import torch
import operator
import random
import numpy as np
from collections import deque
import time
import os
from torch.utils.tensorboard import SummaryWriter
from torch.nn import functional as F
import datetime
from functools import reduce
from matplotlib import pyplot as plt

from .base import BaseMethod
from .memories.inmemory_replay import InMemoryReplay
from . import common

class MLP(torch.nn.Module):
    def __init__(self, state_size, num_actions):
        super(MLP, self).__init__()
        self.fc1 = torch.nn.Linear(state_size, 128)
        self.fc2 = torch.nn.Linear(128, 256)
        self.fc3 = torch.nn.Linear(256, 128)
        self.fc3 = torch.nn.Linear(128, num_actions)
        self.loss = torch.nn.MSELoss()
        self.optimizer = torch.optim.Adam(self.parameters(), lr=1e-4)
        self.device = torch.device(f"cuda:{0}" if torch.cuda.is_available()
                                   else "cpu")

        self.anneal_until = 300000

    def forward(self, x):
        x = F.relu(self.fc1(x))
        x = F.relu(self.fc2(x))
        x = F.relu(self.fc3(x))
        return x

    def target_q(self, qs, qs_p, qs_p_target, a, r, t):
        f_q = np.copy(qs)
        q = np.argmax(qs_p, axis=1)
        for _i, _t in enumerate(t):
            _r = r[_i]
            _a = a[_i]
            f_q[_i, _a] = _r if _t else _r + qs_p_target[_i, q[_i]] * self.gamma
        return f_q

    def train(self, batch, target=None):
        # memory is built as State x Action x Next State x Reward x Is Terminal
        s, a, s_p, r, t = batch[0], batch[1], batch[2], batch[3], batch[4]
        # s = torch.from_numpy(s)
        # s_p = torch.from_numpy(s_p)
        with torch.no_grad():
            next_state_torch = torch.from_numpy(s_p).type(torch.FloatTensor).to(self.device)
            qs_future = self.forward(next_state_torch)
            # qs_future_target = target.forward(next_state_torch).cpu().data.numpy()
            qs_future_numpy = qs_future.cpu().data.numpy()
        self.optim.zero_grad()
        state_torch = torch.from_numpy(s).type(torch.FloatTensor).to(self.device)
        qs = self.forward(state_torch)
        qs_numpy = qs.cpu().data.numpy()
        f_q = torch.from_numpy(self.target_q(qs_numpy, qs_future_numpy, qs_future_numpy, a, r, t)).to(self.device)
        # print(f_q)
        loss = self.loss(f_q.float(), qs.float())
        loss.backward()
        self.optimizer.step()
        return loss.item()

    def next_action(self, state, steps=None):
        """
        returns the next best action
        defined by argmax(self.net.forward())
        state: an ndarray of the current state, preprocessed
        returns: the index of the best action
        """
        if steps:
            eps = self.eps(steps)
            # eps = self.eps_exp(steps)
            if random.random() <= eps:
                return random.randint(0, self.n_actions-1)
        qs = self.forward(state)
        return torch.max(qs, axis=1)[1].cpu().numpy()[0]

    def eps(self, steps):
        return self.end_eps if steps >= self.anneal_until else \
            self.start_eps - ((self.start_eps - self.end_eps) /
            self.anneal_until * steps)

    def parameter_count(self):
        return sum(map(lambda x: reduce(operator.mul, x.shape, 1), self.parameters()))

class DQN(BaseMethod):

    def __init__(self, env, state, problem=0, params=None, action_list=None):
        # self, params, actions, input_shape=(4, 64, 64)):
        self.params = params if params is not None \
            else common.DEFAULT_PARAMS
        self.env = env
        self.env.fix_problem_index(problem)
        self.problem = problem
        self.batch_size = self.params['batch_size']
        self.memory = InMemoryReplay(size=self.params['mem_size'], input_shape=self.params['input_shape'])
        self.test_memory = InMemoryReplay(size=self.params['dry_size'], input_shape=self.params['input_shape'])
        self.curr_state = deque(maxlen=self.params['history'])
        self.next_state = deque(maxlen=self.params['history'])
        self.net = MLP(90, len(action_list))
        self.average_qs = []
        self.max_timesteps = 50

        self.predicates = env.observation_space.predicates

        self.blocks = ['d', 'r', 'a', 'w', 'o', 'e', 'p', 'c']

        if action_list is None:
            self.action_list = list(env.action_space.all_ground_literals(state, valid_only=False))
        else:
            self.actions = action_list

        self.extract_offsets()
        # self.train_skip = 8
        # print(f'RND has {self.rnd.count_parameters()} parameters.')


    def build_state(self, obs):
        state = [0. for _ in range(self.state_length)]
        ground_literals = obs[0]
        print(ground_literals)
        for lit in ground_literals:
            base_offset = self.offsets[lit.predicate.name]
            var_offset = 1
            for v in lit.variables:
                if v.var_type == 'block':
                    var_offset *= self.blocks.index(v.name)
                else:
                    var_offset = 0
            print('Offsets:',base_offset, var_offset, base_offset + var_offset)
            state[base_offset + var_offset] = 1.
        return state

    def extract_offsets(self):
        offsets = {}
        i = 0
        for pred in self.predicates:
            print(pred.__dict__)
            offsets[pred.name] = i
            num_lits = 1
            for t in pred.var_types:
                if t == 'block':
                    num_lits *= len(self.blocks)
            i += num_lits
        self.state_length = i
        self.offsets = offsets

    def literal_from_vector(self, vector):
        max_q_value = np.argmax(vector)
        return self.actions[max_q_value]

    def loss(self, qs, qs_p, qs_p_target, a, r, t):
        # torch.from_numpy
        return self.future_q(qs, qs_p, qs_p_target, a, r, t)
        # return [qs[i] if i != a else r for i in range(self.n_actions)]

    def future_q(self, qs, qs_p, qs_p_target, a, r, t):
        f_q = np.copy(qs)
        q = np.argmax(qs_p, axis=1)
        for _i, _t in enumerate(t):
            _r = r[_i]
            _a = a[_i]
            f_q[_i, _a] = _r if _t else _r + qs_p_target[_i, q[_i]] * self.gamma
        return f_q

    def dry_run(self):

        for episode in range(self.params['episodes']):
            pass

    def learn(self):
        # init doom env
        # load config
        training_steps = 1
        skip = 0
        print(f'Training model {type(self.net).__name__}. Parameters: {self.net.parameter_count():,d}.')
        # self.dry_run(self.params['dry_size'])
        writer = self.create_tensorboard()
        # s, _, _, _, _ = self.test_memory.get_batch(10)
        # s = torch.from_numpy(s).to(self.net.device)
        # writer.add_graph(self.net, input_to_model=s, verbose=True)
        for episode in range(self.params['episodes']):
            episode_loss = 0.
            episode_r = 0.

            obs, _ = self.env.reset()
            done = False
            start_time = time.time()
            timestep = 0
            while timestep < self.max_timesteps and not done:


                state = self.build_state(obs)

                _a = self.net.next_action(state, training_steps)
                action = self.literal_from_bits(_a)
                # r = self.apply_action(a)
                # i_r = self.rnd_reward(s).detach().clamp(-1., 1.).item()
                # r = self.normalize_reward(r)
                # r_combined = r + i_r
                # print(r_combined)

                obs, r, done, _ = self.env.step(action)
                next_state = self.bit_from_obs(obs)
                # if done:
                #     next_state = state
                # else:
                #     next_state = self.doom.get_state().screen_buffer

                # s_p = self.state_to_net_state(next_state, self.next_state)

                self.memory.add_transition(state, action, next_state, r, done)

                if skip == self.train_skip:
                    batch = self.memory.get_batch(self.batch_size)
                    if not batch:
                        continue

                    loss = self.net.train(batch, self.target_net)
                    episode_loss += loss
                    # self.train_rnd(batch[0])
                    training_steps += 1
                    skip = 0
                else:
                    skip += 1

                timestep += 1

                # if training_steps % 5000 == 0:
                #     self.target_net.load_state_dict(self.net.state_dict())

                # if training_steps % 10000 == 0:
                #     self.serialize_model(training_steps)
                episode_r += r

            elapsed_time = time.time() - start_time
            avg_q = self.average_q_test()
            self.write_tensorboard(writer, episode_loss, episode_r, avg_q)
            self.average_qs.append(avg_q)
            print(f'Episode {episode} ended. Time to process: {elapsed_time}. Reward earned: {episode_r}. Episode loss: {episode_loss}. Avg. Q after episode: {avg_q}')

            self.curr_state.clear()
            self.next_state.clear()


    def create_tensorboard(self):
        src_dir = os.environ['RLROOT']
        scenario = self.env.domain.domain_name
        log_path = f'{src_dir}/logs/{scenario}/{type(self.net).__name__}/try_{time.time()}'
        os.makedirs(log_path, exist_ok=True)
        return SummaryWriter(log_dir=log_path)

    def write_tensorboard(self, w, l, r, q):
        w.add_scalar('Reward per episode', r)
        w.add_scalar('Avg Q per episode', q)
        w.add_scalar('Loss per episode', l)
        w.flush()

    def normalize_reward(self, r):
        return r

    def average_q_test(self):
        qs = np.zeros((self.test_memory.max_size))
        for i in range(0, len(self.test_memory.s), 32):
            end = min(i + 32, self.test_memory.curr)
            s = self.test_memory.s[i:end]
            s_net = self.net.to_net(s)
            qs[i:end] = torch.max(self.net.forward(s_net), axis=1)[0].cpu().data.numpy()
        qs = np.sum(qs) / self.test_memory.max_size
        return qs

    def serialize_model(self, steps):
        base_dir = os.environ['VZD_TORCH_DIR']
        scenario = self.params['doom_config'].split('/')[-1].split('.')[0]
        scenario_dir = f'{base_dir}/weights/{scenario}'
        os.makedirs(scenario_dir, exist_ok=True)
        path = f'{scenario_dir}/{self.net.name}_{scenario}_{time.time()}.pt'
        torch.save(self.net.state_dict(), path)

    # def build_action(self, a):
    #     return [1 if a == i else 0 for i in range(self.net.actions)]


    # def rnd_reward(self, s):
    #     s_rnd = self.net.to_net(s)
    #     f_rnd = self.rnd.forward(s_rnd)
    #     with torch.no_grad():
    #         f_target = self.target_rnd.forward(s_rnd).detach()
    #     return torch.pow(f_target - f_rnd, 2).sum()

    # def train_rnd(self, s):
    #     self.rnd.optim.zero_grad()
    #     t = self.rnd_reward(s)
    #     # y_pred = self.rnd.forward(s_rnd)
    #     # y_true = self.target_rnd.forward(s_rnd)
    #     t.backward()
    #     self.rnd.optim.step()