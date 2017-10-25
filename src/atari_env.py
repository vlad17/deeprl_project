"""Wrappers for Atari playing, adopted from Deep RL HW3 starter code."""

from collections import deque

import cv2
import gym
from gym import spaces
import numpy as np

from multiprocessing_env import MultiprocessingEnv

class _NoopResetEnv(gym.Wrapper):
    """
    Sample initial states by taking random number of no-ops on reset.
    No-op is assumed to be action 0.
    """
    def __init__(self, env=None, noop_max=30):
        super(_NoopResetEnv, self).__init__(env)
        self.noop_max = noop_max
        assert env.unwrapped.get_action_meanings()[0] == 'NOOP'

    def _reset(self, **_):
        """ Do no-op action for a number of steps in [1, noop_max]."""
        self.env.reset()
        noops = np.random.randint(1, self.noop_max + 1)
        for _ in range(noops):
            obs, _, _, _ = self.env.step(0)
        return obs

class _FireResetEnv(gym.Wrapper):
    """Take action on reset for environments that are fixed until firing."""
    def __init__(self, env=None):
        super(_FireResetEnv, self).__init__(env)
        assert env.unwrapped.get_action_meanings()[1] == 'FIRE'
        assert len(env.unwrapped.get_action_meanings()) >= 3

    def _reset(self, **_):
        self.env.reset()
        obs, _, _, _ = self.env.step(1)
        obs, _, _, _ = self.env.step(2)
        return obs

class _EpisodicLifeEnv(gym.Wrapper):
    """
    Make end-of-life == end-of-episode, but only reset on true game over.
    Done by DeepMind for the DQN since it helps value estimation.
    """
    def __init__(self, env=None):
        super(_EpisodicLifeEnv, self).__init__(env)
        self.lives = 0
        self.was_real_done = True
        self.was_real_reset = False

    def _step(self, action):
        obs, reward, done, info = self.env.step(action)
        self.was_real_done = done
        # check current lives, make loss of life terminal,
        # then update lives to handle bonus lives
        lives = self.env.unwrapped.ale.lives()
        if lives < self.lives and lives > 0:
            # for Qbert somtimes we stay in lives == 0 condtion for a few
            # frames so its important to keep lives > 0, so that we only reset
            # once the environment advertises done.
            done = True
        self.lives = lives
        return obs, reward, done, info

    def _reset(self, **_):
        """
        Reset only when lives are exhausted.
        This way all states are still reachable even though lives are episodic,
        and the learner need not know about any of this behind-the-scenes.
        """
        if self.was_real_done:
            obs = self.env.reset()
            self.was_real_reset = True
        else:
            # no-op step to advance from terminal/lost life state
            obs, _, _, _ = self.env.step(0)
            self.was_real_reset = False
        self.lives = self.env.unwrapped.ale.lives()
        return obs

class _MaxAndSkipEnv(gym.Wrapper):
    """Return only every `skip`-th frame"""
    def __init__(self, env=None, skip=4):
        super(_MaxAndSkipEnv, self).__init__(env)
        # most recent raw observations (for max pooling across time steps)
        self._obs_buffer = deque(maxlen=2)
        self._skip = skip

    def _step(self, action):
        total_reward = 0.0
        done = None
        for _ in range(self._skip):
            obs, reward, done, info = self.env.step(action)
            self._obs_buffer.append(obs)
            total_reward += reward
            if done:
                break

        max_frame = np.max(np.stack(self._obs_buffer), axis=0)

        return max_frame, total_reward, done, info

    def _reset(self, **_):
        """Clear past frame buffer and init. to first obs. from inner env."""
        self._obs_buffer.clear()
        obs = self.env.reset()
        self._obs_buffer.append(obs)
        return obs

def _process_frame84(frame):
    img = np.reshape(frame, [210, 160, 3]).astype(np.float32)
    img = img[:, :, 0] * 0.299 + img[:, :, 1] * 0.587 + img[:, :, 2] * 0.114
    resized_screen = cv2.resize(
        img, (84, 110), interpolation=cv2.INTER_LINEAR)
    x_t = resized_screen[18:102, :]
    x_t = np.reshape(x_t, [84, 84, 1])
    return x_t.astype(np.uint8)

class _ProcessFrame84(gym.Wrapper):
    """Wrapper to pre-process (rescale, greyscale) observations."""
    def __init__(self, env=None):
        super(_ProcessFrame84, self).__init__(env)
        self.observation_space = spaces.Box(low=0, high=255, shape=(84, 84, 1))

    def _step(self, action):
        obs, reward, done, info = self.env.step(action)
        return _process_frame84(obs), reward, done, info

    def _reset(self, **_):
        return _process_frame84(self.env.reset())

class _ClippedRewardsWrapper(gym.Wrapper):
    """Wrapper that clips gym rewards"""
    def _step(self, action):
        obs, reward, done, info = self.env.step(action)
        return obs, np.sign(reward), done, info

def _wrap_deepmind_ram(env):
    """Applies various Atari-specific wrappers to make learning easier."""
    env = _EpisodicLifeEnv(env)
    env = _NoopResetEnv(env, noop_max=30)
    env = _MaxAndSkipEnv(env, skip=4)
    if 'FIRE' in env.unwrapped.get_action_meanings():
        env = _FireResetEnv(env)
    env = _ClippedRewardsWrapper(env)
    return env

def _wrap_deepmind(env):
    """Applies various Atari-specific wrappers to make learning easier."""
    assert 'NoFrameskip' in env.spec.id
    env = _EpisodicLifeEnv(env)
    env = _NoopResetEnv(env, noop_max=30)
    env = _MaxAndSkipEnv(env, skip=4)
    if 'FIRE' in env.unwrapped.get_action_meanings():
        env = _FireResetEnv(env)
    env = _ProcessFrame84(env)
    env = _ClippedRewardsWrapper(env)
    return env

def gen_pong_env(seed):
    """Generate a pong environment, with all the bells and whistles."""
    benchmark = gym.benchmark_spec('Atari40M')
    task = benchmark.tasks[3]

    env_id = task.env_id
    env = gym.make(env_id)
    env.seed(seed)

    # Can wrap in gym.wrappers.Monitor here if we want to record.
    env = _wrap_deepmind(env)
    return env

def gen_pong_ram_env(seed):
    """Generate a pong RAM environment, with all the bells and whistles."""
    env = gym.make("Pong-ram-v0")
    env.seed(seed)
    # Can wrap in gym.wrappers.Monitor here if we want to record.
    env = _wrap_deepmind_ram(env)
    return env
