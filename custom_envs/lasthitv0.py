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

		# if still can't find target, print error and dump env
		if not env.is_done() and (self.target is None or self.target.is_dead()):
			print ("error: can't still find a target is_done=", env.is_done())
			env.info()
			print ("================================")

		# now that you have, attack it once
		self.attack()

	def attack(self):
		# ready to attack?
		old_t = self.time_till_next_attack()
		self.frames_till_next_attack = self.frames_till_next_attack - 1 if self.frames_till_next_attack >= 1 else 0

		if self.frames_till_next_attack > 0:
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

	def set_target(self, target):
		self.target = target

	def time_till_next_attack(self):
		return self.frames_till_next_attack * (1/30)

	def can_attack(self):
		# not perfect but ok
		if len(self.queue) == 0 and self.frames_till_next_attack == 0:
			return 1
		return 0

	def attack(self, env):
		if self.frames_till_next_attack > 0:
			return

		if len(self.queue) > 0:
			return

		self.queue.append((env.ticks+5, 'FIRE'))

	def act(self, env):
		ticks, action = self.queue.pop()

		if action == 'FIRE':
			self.frames_till_next_attack = 42
			self.queue.append((ticks + self.frames_to_hit_target(), 'IMPACT'))

		if action == 'IMPACT':
			self.target.take_dmg(self.dmg)
			if self.target.is_dead():
				env.single_tick_reward += 1
			#else:
			#	env.single_tick_reward += -0.3

			env.forced_done = True

	def frames_to_hit_target(self):
		return math.ceil(self.distance / self.projectile_speed_frames)

	def tick(self, env):
		self.frames_till_next_attack = self.frames_till_next_attack - 1 if self.frames_till_next_attack >= 1 else 0

		if len(self.queue) > 0:
			tick, action = self.queue[0]
			if env.ticks == tick:

				self.act(env)


		return

class LastHitEnv(gym.Env):
	def __init__(self):
		self.reset()

		self.observation_space = spaces.Box(-5, 5, shape=(8,))
		self.action_space = spaces.Discrete(2)

	def reset(self):
		self.forced_done = False
		self.single_tick_reward = 0
		self.reward = 0.005

		self.ticks 		= 0
		self.creeps 	= [ [], [] ]
		creeps_count 	= [ 4,   1 ]

		for i in range(creeps_count[0]):		# count for team radiant
			self.creeps[0].append(creep(0, i))

		for i in range(creeps_count[1]):		# count for team dire
			self.creeps[1].append(creep(1, i + creeps_count[0]))

		self.player = hero()
		self.player.set_target(self.creeps[1][0])

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
		self.fn_to_creeps(lambda creep: creep.tick(self))
		# tick hero
		self.player.tick(self)
		
		

		# set reward for this frame
		self.update_reward()

		self.ticks += 1
		return True

	def render(self):
		self.info()

	def update_reward(self):		
		if self.creeps[1][0].hp < self.player.dmg:
			self.reward = -0.02

	def is_done(self):
		return self.forced_done or self.creeps[1][0].is_dead()

	def state(self):

		dire_time_to_attack = sorted([creep.time_till_next_attack() for creep in self.creeps[0]])
		#dire_time_to_attack = ([creep.time_till_next_attack() for creep in self.creeps[0]])

		return np.array([ 
			self.creeps[1][0].hp / 550,				# dire creep hp 
			self.player.time_till_next_attack(),	# hero time_till_next_attack
			*dire_time_to_attack,					# radiant creeps time_till_next_attack
			self.player.distance / 1000,			# hero distance to dire creep
			self.player.can_attack(),				
		])

	def step(self, action):
		# returns next_state, reward, done, _ = env.step(action)
		# action either 0 or 1
		if action == 1:
			self.player.attack(self)
		
		self.tick()

		reward = self.reward + self.single_tick_reward
		self.single_tick_reward = 0

		return self.state(), reward, self.is_done(), {}

def sample_use():
	env = gym.make('LastHit-v0')

	env.reset()
	for time in range(500):
		#print (env.state())
		action = 1 if time == 152 else 0
		next_state, reward, done, _ = env.step(action)

		#print (next_state)
		print ("tick = %d reward = %.2f done = %d hp = %d\nttna = %.2f(hero) %.2f %.2f %.2f %.2f distance = %d" % (env.ticks, reward, done,*next_state,))

		if done:
			break

#sample_use()

make = gym.make
