import gym
from gym import spaces

import random
import math

import numpy as np

from .simulator.game import Player as GamePlayer
from .simulator.game import get_random_points, refresh_map, setup_pg, render_scene

class NPC(GamePlayer):
	def __init__(self, pos, team_idx, id, hp = 550, dmg = 21):
		self.id = id											# global id, in world
		self.hp = hp
		self.dmg = dmg
		self.target = None
		self.team_idx = team_idx								# 0 for radiant, 1 for dire
		self.frames_till_next_attack = 0

		npc_type = 'Hero' if isinstance(self, Hero) else 'Creep'
		super().__init__(pos, team_idx, npc_type)

	def encode(self, hero):
		x, y = self.rectc_midpoint()
		try:
			attack_animation = 1 if self.queue[0][1] == 'FIRE' else 0 
		except:
			attack_animation = 0

		dist_to_player = self.dist_to_player(hero) / (3 * 800)

		return [ 
			self.team_idx, 					# team index
			self.time_till_next_attack(), 	# time till can attack
			self.hp / 550, 					# hp (normalize w. '/ 550')
			x / 640, 						# x  (normalize w. '/ 640')
			y / 480, 						# y  (normalize w. '/ 480')
			dist_to_player, 				# ? dist to player (normalize w. '/ 3*800')
			attack_animation 				# is_attack_animation_playing
		]

class Creep(NPC):
	def __init__(self, pos, team_idx, id):
		# create npc base
		super().__init__(pos, team_idx, id, hp = 550, dmg = 21)

	def tick(self, env):
		# acquire a target if you don't have a valid one
		if self.target is not None and self.target.is_dead():
			self.animator.set_state('idle')

		if self.target is None or self.target.is_dead():
			for creep in env.creeps[1-self.team_idx]:
				if not creep.is_dead():
					self.target = creep
					#print ("creep id %d acquired target, id = %d" % (self.id, self.target.id))
					break

		if self.animator.state in ['idle', 'walk']:
			self.walk_to_target()
			

		# now that you have, attack it once
		if self.animator.state == 'attack':
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
		return "id: %d\tteam: %s\tpos: %s\tstate: %s\thp: %d\ttime_next_attack: %f" % (self.id, self.team_name(), self.rectc_midpoint(), self.animator.state, self.hp, self.time_till_next_attack())

class Hero(NPC):
	def __init__(self, id):
		self.name = 'sniper'
		self.projectile_speed = 3000
		self.projectile_speed_frames = self.projectile_speed / 30
		self.range = 550
		self.attack_point_frames = 5
		self.attack_backswing_frames = 21
		self.queue = []
		# create npc base
		super().__init__((random.randint(50, 590), random.randint(50, 430)), team_idx=0, id=id, hp=700, dmg=60)

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

	def is_attacking(self):
		# not perfect but ok
		return len(self.queue) != 0 and not self.target.is_dead()			

	def attack(self, env, target_idx):
		if self.frames_till_next_attack > 0:
			return

		if len(self.queue) > 0:
			return

		if self.set_target(env, target_idx):
			self.queue.append((env.ticks + self.attack_point_frames, 'FIRE', {'target': target_idx}))
			self.animator.set_state('attack', frac=0, speed=20/self.attack_point_frames)

	# if projectile is fired, return False
	# otherwise if it's scheduled to fire, clear the queue
	def interrupt_queue(self):
		if len(self.queue) == 0:
			return True

		_, action, _ = self.queue[0]
		if action == 'FIRE':
			self.queue = []
			return True

		return False

	def act(self, env):
		ticks, action, info = self.queue.pop(0)

		if action == 'FIRE':
			self.animator.set_state('idle')

			# no need to act if target dies during attack animation
			if self.target.is_dead():
				return
			self.frames_till_next_attack = 42			
			self.queue.append((ticks + self.frames_to_hit_target(), 'IMPACT', info)) # roughly ~6 frames

		if action == 'IMPACT':
			# if this line is commented you can remove info from dict which holds target_idx
			# since we pre-set it in attack()
			#self.set_target(env, info['target'])

			# target has died before impact, thus it's a noop
			if self.target.is_dead():
				return
			self.target.take_dmg(self.dmg)
			if self.target.is_dead():
				env.single_tick_reward += 2					# LH

				if self.team_idx == self.target.team_idx:
					env.single_tick_reward -= 1			# Deny
					print ('DENY')
					self.target.notification_txt('DENY')
				else:
					print('LASTHIT')
					self.target.notification_txt('LASTHIT')
			else:
				self.target.notification_txt('FAIL')
				env.single_tick_reward += -0.2

				print ('FAILED ATTEMPT TO LH')

			#env.forced_done = True

	def frames_to_hit_target(self):
		return math.ceil(self.dist_to_player(self.target) / self.projectile_speed_frames)

	def tick(self, env):
		self.frames_till_next_attack = self.frames_till_next_attack - 1 if self.frames_till_next_attack >= 1 else 0

		if len(self.queue) > 0:
			tick = self.queue[0][0]
			if env.ticks == tick:			
				self.act(env)

		return


class LastHitEnv(gym.Env):
	def __init__(self):
		setup_pg() # setup pygame stuff

		self.creeps_count =  [ 2,   2 ] # SHOULD BE SAME

		total_creeps = sum(self.creeps_count)

		self.observation_space = spaces.Box(-5, 5, shape=((total_creeps + 1) * 7,))
		self.action_space = dict(
			enum = spaces.Discrete(3),				# action type
			target = spaces.Discrete(total_creeps),	# attack target
			direction = spaces.Discrete(8),			# move direction
		)

	def reset(self):
		self.forced_done = False
		self.single_tick_reward = 0
		self.reward = 0
		self.default_reward = 0.001 #0.005

		self.ticks 		= 0
		self.creeps 	= [ [], [] ]
		creeps_count 	= self.creeps_count

		RADIANT, DIRE = 0, 1
		
		creep_pos = get_random_points((100,300), (100,300), margin=100, count=creeps_count[0])
		for i in range(creeps_count[0]):		# count for team radiant
			self.creeps[0].append(Creep(creep_pos[i], RADIANT, 1 + i))
		
		creep_pos = get_random_points((350,550), (100,300), margin=100, count=creeps_count[1])	
		for i in range(creeps_count[1]):		# count for team dire
			self.creeps[1].append(Creep(creep_pos[i], DIRE, 1 + i + creeps_count[0]))
		
		self.player = Hero(id=1000)
		
		return  self.state()


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

		# map for pathfinding
		refresh_map(self.creeps[0] + self.creeps[1])

		# tick creeps
		self.fn_to_creeps(lambda creep: creep.tick(self) if not creep.is_dead() else None)
		# tick hero
		self.player.tick(self)

		# set reward for this frame
		self.update_reward()

		self.ticks += 1
		return True

	def render(self, force_realtime=False, text_render=False, add_empty_line=False):
		# textual render
		if text_render:
			print ("~ t = %d" % self.ticks)
			self.info()

			if add_empty_line:
				print ()

		# graphical render
		render_scene(self.creeps[0] + self.creeps[1], [self.player], force_realtime)

	def update_reward(self):
		radiant_creeps_killable = [ not creep.is_dead() and creep.hp <= self.player.dmg for creep in self.creeps[0] ]
		dire_creeps_killable = [ not creep.is_dead() and creep.hp <= self.player.dmg for creep in self.creeps[1] ]

		threshold_reward = sum(radiant_creeps_killable) * -0.01 + sum(dire_creeps_killable) * -0.02
		
		if threshold_reward != 0:
			self.reward = threshold_reward
		else:
			self.reward = self.default_reward

		# circularly award based on closeness to target
		alive_creeps = list(filter(lambda c: not c.is_dead(), self.creeps[0] + self.creeps[1]))
		positioning_rewards = [ ((0.75 * self.player.range), self.player.dist_to_player(c)) \
			for c in alive_creeps ]
		positioning_rewards = [ 0.0025 * (min(x,y) / max(x,y)) for x,y in positioning_rewards ]
		positioning_reward = sum(positioning_rewards) / (len(positioning_rewards) + 1e-10)

		self.reward += positioning_reward

	def is_done(self):
		return \
			self.forced_done or \
			sum([1-dire_creep.is_dead() for dire_creep in self.creeps[1]]) == 0 or \
			sum([1-creep.is_dead() for creep in self.creeps[0] + self.creeps[1]]) == 1

	def state(self):
		encodings = [ e.encode(hero=self.player) for e in ([self.player] + self.creeps[0] + self.creeps[1]) ]
		return np.array(encodings).flatten()

	""" 
		env.step(action_dict)
		returns: next_state, reward, done, _ 
	"""
	def step(self, **chosen):
		if chosen['enum'] == [0]:
			# do nothing
			if not self.player.is_attacking():
				self.player.animator.set_state('idle')
		elif chosen['enum'] == [1]:
			# initiate attack if in range
			target_idx = chosen['target'][0]
			target_player = np.array(self.creeps).ravel()[target_idx]

			if self.player.dist_to_player(target_player) <= self.player.range:
				#print ("SHOTS FIRED, DIST = ", self.player.dist_to_player(target_player))
				self.player.attack(self, target_idx)
			#else:
				#print ("NOT IN RANGE, DIST = ", self.player.dist_to_player(target_player))
		elif chosen['enum'] == [2]:
			# move 5 units in chosen direction
			self.player.move_in_direction(chosen['direction'][0])
			self.player.interrupt_queue()

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
		print ("time = ", time)

		if time < 10:
			next_state, reward, done, _ = env.step(enum=[2], direction=[4])
		else:
			next_state, reward, done, _ = env.step(enum=[1], target=[2])

		total_reward += reward
		env.render()

		if done:
			break

	print ("total reward: %s" % total_reward)

#sample_use()

make = gym.make
