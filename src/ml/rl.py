import pickle
import numpy as np
import random

from pddlgym.core import InvalidAction

# This will be an implementation of Q-Learning with Gym

# use epsilon-greedy policies instead of 1 for maximum, 0 otherwise
# test with negative rewards
# policy gradient

# test value iteration with one traj after learning policies (later)


class RLAgent:
    def __init__(self,
                 problem=0,
                 episodes=100,
                 decaying_eps=True,
                 eps=0.9,
                 alpha=0.01,
                 decay=0.00005,
                 gamma=0.99,
                 action_list=None):
        self.problem = problem
        self.episodes = episodes
        self.decaying_eps = decaying_eps
        self.eps = eps
        self.alpha = alpha
        self.decay = decay
        self.gamma = gamma
        self.action_list = action_list

class TabularQLearner(RLAgent):
    def __init__(self,
                 env,
                 init_obs,
                 problem=None,
                 episodes=25000,
                 decaying_eps=True,
                 eps=0.9,
                 alpha=0.01,
                 decay=0.000002,
                 gamma=0.99,
                 action_list=None,
                 **kwargs):
        self.env = env
        if not action_list:
            self.action_list = list(env.action_space.all_ground_literals(init_obs, valid_only=False))
        else:
            self.action_list = action_list
            print(action_list)
        self.actions = len(self.action_list)

        self.q_table = {}

        # hyperparameters
        self.episodes = episodes
        self.gamma = gamma
        self.decay = decay
        self.c_eps = eps
        self.base_eps = eps
        self.patience = 5
        if decaying_eps:

            def epsilon():
                self.c_eps = max(self.c_eps - self.decay, 0.01)

                return self.c_eps

            self.eps = epsilon
        else:
            self.eps = lambda: eps
        self.decaying_eps = decaying_eps
        self.alpha = alpha

        if problem:
            self.env.fix_problem_index(problem)


    def save_q_table(self, path):
        with open(path, 'w') as f:
            pickle.dump(self.q_table, f)

    def load_q_table(self, path):
        with open(path, 'r') as f:
           table = pickle.load(path)
           self.q_table = table

    def add_new_state(self, state):
        self.q_table[state] = [0 for _ in range(self.actions)]

    def best_action(self, state):
        if state not in self.q_table:
            self.q_table[state] = [0 for _ in range(self.actions)]
        return np.argmax(self.q_table[state])


    def get_max_q(self, state):
        if state not in self.q_table:
            self.add_new_state(state)
        return np.max(self.q_table[state])

    def set_q_value(self, state, a, q):
        if state not in self.q_table:
            self.add_new_state(state)
        self.q_table[state][a] = q

    def get_q_value(self, state, a):
        if state not in self.q_table:
            self.add_new_state(state)
        return self.q_table[state][a]

    def learn(self):
        tsteps = 50
        done_times = 0
        patience = 0
        for n in range(self.episodes):
            state, info = self.env.reset()
            state = state.literals
            done = False
            tstep = 0
            while tstep < tsteps and not done:
                eps = self.eps()
                if random.random() <= eps:
                    a = random.randint(0, self.actions-1)
                    # a = self.env.action_space.sample(state)
                else:
                    a = self.best_action(state)
                try:
                    next_state, r, done, _ = self.env.step(self.action_list[a])
                    next_state = next_state.literals
                except InvalidAction:
                    next_state = state
                    r = 0.
                    done = False

                if done:
                    done_times += 1

                next_max_q = self.get_max_q(next_state)
                old_q = self.get_q_value(state, a)

                new_q = old_q + self.alpha * \
                    (r + (self.gamma * next_max_q) - old_q)

                self.set_q_value(state, a, new_q)
                state = next_state
                tstep += 1
            if (n + 1) % 1000 == 0:
                print(f'Episode {n} finished. Timestep: {tstep}. Done: {done}. Reached the goal {done_times} times during this interval. Eps = {eps}')
                if done_times <= 10:
                    patience += 1
                    if patience >= self.patience:
                        print(f"Did not find goal after {n} episodes. Retrying.")
                        raise ValueError("Did not learn")
                else:
                    patience = 0
                done_times = 0
        print(len(self.q_table.keys()))