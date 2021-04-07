import gym
from gym import spaces

import random
import math

import numpy as np

class creep:

	def __init__(self, team_idx, id):
		self.team_idx = team_idx								# 0 for radiant, 1 for dire
		self.id = id											# global id, in world
		self.frames_till_next_attack = random.randint(0, 10)	# noise to make it interesting
		self.hp = 550
		self.target = None
		self.dmg = 21

	def tick(self, env):
		# acquire a target if you don't have a valid one
		if self.target is None or self.target.is_dead():
			for creep in env.creeps[1-self.team_idx]:
				if not creep.is_dead():
					self.target = creep
					#print ("creep id %d acquired target, id = %d" % (self.id, self.target.id))
					break

		"""
		# if still can't find target, print error and dump env
		if not env.is_done() and (self.target is None or self.target.is_dead()):
			print ("error: can't still find a target is_done=", env.is_done())
			env.info()
			print ("================================")
		"""

		# now that you have, attack it once
		self.attack()

	def attack(self):
		# ready to attack?
		old_t = self.time_till_next_attack()
		self.frames_till_next_attack = self.frames_till_next_attack - 1 if self.frames_till_next_attack >= 1 else 0

		# dead target happens in case we don't have a new target and locked on previous,dead target
		if self.frames_till_next_attack > 0 or self.target.is_dead():
			#print ("creep id %d not ready to attack t = %f -> %f" %
			#		(self.id, old_t, self.time_till_next_attack()))
			return

		#self.target.hp = self.target.hp - self.dmg if self.target.hp >= self.dmg else 0
		self.target.take_dmg(self.dmg)
		self.frames_till_next_attack = 30

	def take_dmg(self, dmg):
		self.hp = self.hp - dmg if self.hp >= dmg else 0

	def time_till_next_attack(self):
		return self.frames_till_next_attack * (1/30)

	def is_dead(self):
		return self.hp == 0

	def team_name(self):
		return "radiant" if self.team_idx == 0 else "dire"

	def info(self):
		return "id: %d\tteam: %s\thp: %d\ttime_next_attack: %f" % (self.id, self.team_name(), self.hp, self.time_till_next_attack())

class hero:
	def __init__(self):
		self.dmg = 60
		self.name = 'sniper'
		self.projectile_speed = 3000
		self.projectile_speed_frames = self.projectile_speed / 30
		self.distance = 550
		self.frames_till_next_attack = 0
		self.attack_point_frames = 5
		self.attack_backswing_frames = 21
		self.target = None
		self.queue = []
		self.team_idx = 0

	def set_target(self, env, idx):
		y_dim = len(env.creeps[0])
		x = idx // y_dim
		y = idx % y_dim
		#print ("target (x,y) = %s %s Y_dim=%d, idx=%d" % (x,y, y_dim, idx))
		self.target = env.creeps[x][y]
		if not self.target.is_dead():
			return True
		else:
			self.target = None
			return False

	def time_till_next_attack(self):
		return self.frames_till_next_attack * (1/30)

	def can_attack(self):
		# not perfect but ok
		if len(self.queue) == 0 and self.frames_till_next_attack == 0:
			return 1
		if len(self.queue) != 0 and self.target.is_dead():
			self.queue = []
			return 1
		return 0

	def attack(self, env, target_idx):
		if self.frames_till_next_attack > 0:
			return

		if len(self.queue) > 0:
			return

		if self.set_target(env, target_idx):
			self.queue.append((env.ticks+5, 'FIRE', {'target': target_idx}))

	def act(self, env):
		ticks, action, info = self.queue.pop()

		if action == 'FIRE':
			# no need to act if target dies during attack animation
			if self.target.is_dead():
				return
			self.frames_till_next_attack = 42
			self.queue.append((ticks + self.frames_to_hit_target(), 'IMPACT', info))

		if action == 'IMPACT':
			# if this line is commented you can remove info from dict which holds target_idx
			# since we pre-set it in attack()
			#self.set_target(env, info['target'])

			# target has died before impact, thus it's a noop
			if self.target.is_dead():
				return
			self.target.take_dmg(self.dmg)
			if self.target.is_dead():
				env.single_tick_reward += 1					# LH
				if self.team_idx == self.target.team_idx:
					env.single_tick_reward -= 0.5			# Deny
			else:
				env.single_tick_reward += -0.2

			#env.forced_done = True

	def frames_to_hit_target(self):
		return math.ceil(self.distance / self.projectile_speed_frames)

	def tick(self, env):
		self.frames_till_next_attack = self.frames_till_next_attack - 1 if self.frames_till_next_attack >= 1 else 0

		if len(self.queue) > 0:
			tick = self.queue[0][0]
			if env.ticks == tick:			
				self.act(env)

		return


class LastHitEnv(gym.Env):
	def __init__(self):
		self.reset()

		self.observation_space = spaces.Box(-5, 5, shape=(19,))
		self.action_space = dict(
			enum = spaces.Discrete(2),
			target = spaces.Discrete(8),
		)

	def reset(self):
		self.forced_done = False
		self.single_tick_reward = 0
		self.reward = 0
		self.default_reward = 0.001 #0.005

		self.ticks 		= 0
		self.creeps 	= [ [], [] ]
		creeps_count 	= [ 4,   4 ] 

		for i in range(creeps_count[0]):		# count for team radiant
			self.creeps[0].append(creep(0, i))
			
		for i in range(creeps_count[1]):		# count for team dire
			self.creeps[1].append(creep(1, i + creeps_count[0]))

		self.player = hero()

		return self.state()


	def info(self):
		self.fn_to_creeps(lambda creep: print(creep.info()))
		#return self.creeps

	# lists all creeps and applies fn to each of them
	# fn(c1), fn(c2), ...
	def fn_to_creeps(self, fn):
		for team in self.creeps:
			for creep in team:
				fn(creep)
		

	def tick(self):
		if self.is_done():
			return False

		# tick creeps
		self.fn_to_creeps(lambda creep: creep.tick(self) if not creep.is_dead() else None)
		# tick hero
		self.player.tick(self)

		# set reward for this frame
		self.update_reward()

		self.ticks += 1
		return True

	def render(self, add_empty_line=False):
		print ("~ t = %d" % self.ticks)
		self.info()
		if add_empty_line:
			print ()

	def update_reward(self):
		
		radiant_creeps_killable = [ not creep.is_dead() and creep.hp <= self.player.dmg for creep in self.creeps[0] ]
		dire_creeps_killable = [ not creep.is_dead() and creep.hp <= self.player.dmg for creep in self.creeps[1] ]

		threshold_reward = sum(radiant_creeps_killable) * -0.01 + sum(dire_creeps_killable) * -0.02
		
		if threshold_reward != 0:
			self.reward = threshold_reward
		else:
			self.reward = self.default_reward

	def is_done(self):
		return \
			self.forced_done or \
			sum([1-dire_creep.is_dead() for dire_creep in self.creeps[1]]) == 0

	def state(self):

		radiant_time_to_attack = [creep.time_till_next_attack() for creep in self.creeps[0]]
		dire_time_to_attack = [creep.time_till_next_attack() for creep in self.creeps[1]]

		radiant_hp_n = [creep.hp / 550 for creep in self.creeps[0]]
		dire_hp_n = [creep.hp / 550 for creep in self.creeps[1]]

		return np.array([ 
			self.player.can_attack(),				# player stats
			self.player.time_till_next_attack(),	# hero time_till_next_attack
			self.player.distance / 1000,			# hero distance to dire creep

			*radiant_hp_n,							# radiant creeps hp 
			*dire_hp_n,								# dire creeps hp 

			*radiant_time_to_attack,				# radiant creeps time_till_next_attack
			*dire_time_to_attack,					# dire creeps time_till_next_attack
		])

	def step(self, **chosen):
		# returns next_state, reward, done, _ = env.step(action)
		if chosen['enum'] == [0]:
			pass
		elif chosen['enum'] == [1]:
			self.player.attack(self, chosen['target'][0])
		
		self.tick()

		reward = self.reward + self.single_tick_reward
		self.single_tick_reward = 0

		return self.state(), reward, self.is_done(), {}

def sample_use():
	random.seed(1337)
	env = LastHitEnv()
	total_reward = 0

	env.reset()
	env.render(add_empty_line=True)
	for time in range(1500):
		#print (env.state())

		#t_ = 1224

		score_table = {148: 5, 383: 6, 443: 2, 712: 7, 919: 3, 1224: 8}		

		action = score_table[time] if time in score_table else 0
		next_state, reward, done, _ = env.step(enum=1, target=0)
		total_reward += reward
		env.render()
		print (next_state)
		print ("reward = %.4f\t done = %s\n" % (reward, done))

		#animation_gap = [ j for i in [list(range(k,k+47)) for k in score_table] for j in i ]
		#animation_gap = sum([list(range(k,k+47)) for k in score_table], [])
		#if reward < 0 and time in animation_gap:
		#	return

		#if time == t_+11:
		#	break

		if done:
			break

	print ("total reward: %s" % total_reward)


#sample_use()

make = gym.make
