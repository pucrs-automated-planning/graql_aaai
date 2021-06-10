import collections
from typing import Collection
from matplotlib import pyplot as plt
import numpy as np
from math import log2
import random
import os

from numpy.core.fromnumeric import mean

def kl_divergence(p1, p2):
    return sum(p1[i] * log2(p1[i]/p2[i]) for i in range(len(p1)))

def kl_divergence_per_plan_state(trajectory, p1, p2, epsilon=0., actions=24):
    p1 = values_to_policy(p1, epsilon)
    p2 = values_to_policy(p2, epsilon)

    per_state_divergence = []
    for state in trajectory:
        if state not in p1:
            p1[state] = [1e-6 + epsilon/actions for _ in range(actions)]
            random_best_action = random.choice(range(actions))
            p1[state][random_best_action] = 1. - 1e-6*(actions-1) - epsilon
        if state not in p2:
            p2[state] = [1e-6 + epsilon/actions for _ in range(actions)]
        qp1 = p1[state]
        qp2 = p2[state]
        per_state_divergence.append(kl_divergence(qp1, qp2))
    return per_state_divergence


def kl_divergence_norm(traj, p, actions, epsilon=0.):
    p_traj = traj_to_policy(traj, actions)
    # p1 = values_to_policy(p1, epsilon)
    policy = values_to_policy(p, epsilon)

    distances = []
    for i, state in enumerate(p_traj):
        if state not in policy:
            add_dummy_q(policy, state, actions, epsilon)
        qp1 = p_traj[state]
        qp2 = policy[state]
        # print(f'Best action for traj and policy, state {i}: {np.argmax(qp1)} - {np.argmax(qp2)}')
        distances.append(kl_divergence(qp1, qp2))
    return mean(distances)

def add_dummy_q(policy, state, actions, epsilon=0.):
    n_actions = len(actions)
    policy[state] = [1e-6 + epsilon/n_actions for _ in range(n_actions)]
    best_random_action = random.choice(range(n_actions))
    policy[state][best_random_action] = 1. - epsilon - 1e-6*(n_actions-1)

def kl_divergence_mean(p1, p2):

    pass

def traj_to_policy(traj, actions, epsilon=0.):
    trajectory_as_police = {}
    for state, action in traj:
        action_index = actions.index(action)
        actions_len = len(actions)
        qs = [1e-6 + epsilon/actions_len for _ in range(actions_len)]
        qs[action_index] = 1. - 1e-6 * (actions_len-1) - epsilon
        trajectory_as_police[state] = qs
    return trajectory_as_police

def values_to_policy(policy, epsilon=0.):
    policy_table = {}
    for s in policy.keys():
        q = policy[s]
        l = len(q)
        policy_table[s] = [1e-6 + epsilon/l for _ in range(l)]
        policy_table[s][np.argmax(q)] = 1. - 1e-6*(l-1) - epsilon
    return policy_table


def plot_traj_policy_divergence(goal, eps, *kls):
    fig = plt.figure()
    ax = fig.add_axes([0,0,1,1])
    combinations = [f'KL(t{goal}, p{n}' for n in range(len(kls))]
    ax.bar(combinations, kls)
    ax.set(title=f'Eps = {eps}')
    plt.show()

def plot_mean_divergence(goal, eps, *divs):
    # fig, ax  = plt.subplots()
    fig, ax = plt.subplots()
    plt.title(f'Divergence between trajectory for goal {goal} and policies. Eps = {eps}')
    goals_text = [f'p{n}' for n in range(len(divs))]
    plt.bar(goals_text, divs)
    save_path = os.path.abspath('../imgs')
    for i, d in enumerate(divs):
        ax.text(i, d + 1.5, f'{d:.2f}')
    ax.set_ylim([0., 25.])
    plt.savefig(f'{save_path}/goal_{goal}_eps_{eps}.jpg')
    plt.show()


def divergence_table(ds, goals):
    for n in range(goals):
        d = ds[f'p{n}']

    pass