import os

os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
import pygame as pg

import time
import random
import math

import numpy as np

from pygame.locals import *

#Setting up FPS 
FPS = 30

RADIANT = 'radiant'
DIRE = 'dire'

WHITE  = (255,255,255)
BLACK  = (0  ,  0,  0)
GREEN  = (0  ,255,  0)
RED    = (255,  0,  0)
YELLOW = (255,255,  0) 


OPPOSING = { RADIANT: DIRE, DIRE: RADIANT }
ALL = { RADIANT: pg.sprite.Group(), DIRE: pg.sprite.Group() }

DIRECTIONS = [ np.array([np.cos(deg),np.sin(deg)]) for deg in  [ i * 2 * np.pi / 8 for i in range(8) ] ]

NOTIFICATIONS = []

def scale_image(img, factor):
	return pg.transform.scale(img, (int(img.get_width()*factor),int(img.get_height()*factor)) )

class Animator:

	def __init__(self, team, npc_type):
		self.state = 'idle'
		self.images = {'idle':[], 'walk':[], 'attack': []}
		self.apos = 0 		# animation position (x/20)
		self.aspeed = 20/30	# animation speed
		self.frame = 0		# frame out of fps   (x/30)
		self.face_east = True

		dir_path = os.path.dirname(os.path.realpath(__file__))
		template = 'PNG/3/3_enemies_1_%s_%.3d.png' if team == RADIANT else 'PNG/7/7_enemies_1_%s_%.3d.png' 
		if npc_type == 'Hero':
			template = 'PNG/2/2_enemies_1_%s_%.3d.png' if team == RADIANT else 'PNG/4/4_enemies_1_%s_%.3d.png'

		for k in self.images:
			for i in range(20):
				img_addr = dir_path + '/' + template % (k, i)
				img = pg.image.load(img_addr)
				img_resized = scale_image(img, 0.25)
				self.images[k].append( img_resized )
			
		self.image = self.images['idle'][self.apos]

	def get_image(self):
		self.frame = (self.frame + 1) % 30
		self.apos = int(self.frame * self.aspeed % 20)
		self.image = self.images[self.state][self.apos]
		return self.image if self.face_east else pg.transform.flip(self.image, True, False)

	def set_state(self, state, frac=0., speed=2/3):
		# state { idle , walking, attacking, etc }
		# frac [0, 1] how far we are into animation
		self.state = state
		self.aspeed = speed
		if frac >= 0.:
			self.frame = int(frac * 30) % 30

class Healthbar:
	def __init__(self, player, max_val):
		self.player = player
		self.value = self.max = max_val

	def draw(self, surface):
		rect = self.player.rectc
		
		rect.width = max(self.player.rectc.width, 41) #max([ (o.rectc.width) for o in [*ALL[RADIANT],*ALL[DIRE]] ])
		
		rect.top -= rect.width * .18
		rect.height = rect.width * .1875

		pg.draw.rect(surface, BLACK, rect, 3) 	# outline
		pg.draw.rect(surface, GREEN, rect) 		# green	part	
		
		rect_red = rect.copy()

		rect_red.width = int(rect.width * ((self.max - self.player.hp) / self.max))
		rect_red.left = rect.left + (rect.width - rect_red.width)
		rect_red.top = rect.top
		rect_red.height = rect.height

		pg.draw.rect(surface, RED, rect_red) 	# red part

		

class Player(pg.sprite.Sprite):

	def __init__(self, pos, team, npc_type='Creep'):
		super().__init__()

		self.team = RADIANT if team == 0 else DIRE

		self.animator = Animator(self.team, npc_type)
		self.image = self.animator.get_image()
		self.rect = self.image.get_rect(center=pos)

		self.healthbar = Healthbar(self, self.hp)

	@property
	def rectc(self):
		rectc = self.rect.copy()
		rectc.left += rectc.width * (0.15 if self.animator.face_east else 0.35)
		rectc.width *= 0.5

		rectc.top += rectc.height * 0.15
		rectc.height *= 0.8
		return rectc

	def rectc_midpoint(self):
		rectc = self.rectc
		return (rectc.left + rectc.width/2, rectc.top + rectc.height/2)

	def dist_to_player(self, p):
		delta = np.array(p.rectc_midpoint()) - np.array(self.rectc_midpoint())
		return 3 * math.hypot(*delta)

	@property
	def rectc3(self):
		rectc3 = self.rectc
		rectc3.height = int(rectc3.height/3)
		return rectc3	

	def walk_to_target(self):
		if self.animator.state == 'attack':
			return

		if self.target is None:
			self.animator.state = 'idle'
			return

		target_x = self.target.rectc.left + (-1 if self.animator.face_east else self.target.rectc.width + 1)
		target_top = self.target.rectc.top

		#print ([self.id], "target (id=%d, left=%d, top=%d, map=%d)" % (self.target.id, target_x, target_top, MAP[target_x][target_top]))

		if MAP[target_x][target_top:target_top + self.target.rectc.height].sum() == 0:
			#print ([self.id], "reserving...")
			# reserve it
			MAP[target_x-(self.rectc.width-1) : target_x+1, target_top : target_top+self.rectc3.height+1] = self.id
			#print ("MAP[%d:%d][%d:%d]  is  %d " % (target_x-(self.rectc.width-1), target_x+1, target_top, target_top + self.rectc3.height+1, MAP[target_x][target_top]))
		elif MAP[target_x][target_top] == self.id:
			# special case already mine, no need to reserve
			#print ([self.id], "already owned, no need to reserve")
			pass
		else:
			offset, OFFSET_GAP, next_spot_bottom, next_spot_top = 1, 20, False, False

			while not next_spot_bottom and not next_spot_top:
				if target_top+offset+OFFSET_GAP < 480:
					target_map = MAP[target_x][target_top+offset:target_top+offset+OFFSET_GAP]
					next_spot_bottom = target_map[(target_map != self.id)].sum() == 0

				if target_top-offset >= 0:
					target_map = MAP[target_x][target_top-offset:target_top-offset+OFFSET_GAP]
					next_spot_top = target_map[(target_map != self.id)].sum() == 0

				offset += 1

			#print ([self.id], "offset is %d - bottom? %s" % (offset,next_spot_bottom))

			target_top += offset if next_spot_bottom else -offset

			if target_top < 480 and MAP[target_x][target_top] == 0:
				#print ("found new spot target_top=%d" % target_top)
				# claim it
				for j in range(target_top, target_top + self.rectc3.height + 1):
					if j >= 480: break
					#print ("claimed target_top=%d" % j)
					MAP[target_x][j] = self.id	

		# didn't find a spot
		if target_top >= 480 or target_top > self.target.rectc.top + self.target.rectc.height :
			self.animator.state = 'idle'
			#print ([self.id], "no target locked(target_top=%d)" % (target_top))
			return


		inside_margin = 15 * int((target_top-self.target.rectc.top) / self.rectc3.height)
		inside_margin = abs(inside_margin)
		#print ([self.id], "*NEW* target(top=%d, left_margin=%d)" % (target_top, inside_margin))

		"""
		any target is valid from 
			X = (self.target.rectc.left - self.rectc.width)
		    &
			(self.target.rect.top + self.target.rect.height) <= Y <= self.target.rect.top  
		"""
		delta_x = target_x - self.rectc.left
		delta_y = target_top - self.rectc.top
		delta_size = np.sqrt(delta_x**2 + delta_y**2)

		#print ([self.id], "delta (x=%d,y=%d,size=%d)" % (delta_x, delta_y, delta_size))

		self.animator.state = 'walk'

		delta_x -= self.target.rectc.width - inside_margin
		delta_size = np.sqrt(delta_x**2 + delta_y**2)

		dist_to_target = np.sqrt( (self.target.rectc.left - self.rectc.left)**2 + (self.target.rectc.top - self.rectc.top)**2 )
		
		#print ([self.id], "dist to target ====== %d" % dist_to_target, self.dist_to_player(self.target))

		if delta_size < 5 or dist_to_target < 35:
			self.animator.state = 'attack'
		else:
			delta_x *= (5. / delta_size) if delta_size != 0 else 0 
			delta_y *= (5. / delta_size) if delta_size != 0 else 0

			self.rect.move_ip(delta_x, delta_y)

		# DEBUG line
		#print ([self.id], "line from (%d,%d) -> (%d, %d)" % (self.rectc.left, self.rectc.top, target_x, target_top))
		#pg.draw.line(screen, BLACK, (self.rectc.left, self.rectc.top), (target_x, target_top))

	def move_in_direction(self, direction, units=5):
		self.rect.move_ip(*DIRECTIONS[direction]*units)
		self.animator.state = 'walk'

	def debug_idx_txt(self):
		id_ = self.id if hasattr(self,'id') else 0
		text = font.render('id: %d' % id_, True, BLACK, WHITE)
		text_rect = text.get_rect()
		x = self.rectc.left + (-30 if self.animator.face_east else 25 + self.rectc.width)
		y = self.rectc.top + self.rectc.height//2
		text_rect.center = (x, y)
		return text, text_rect

	def notification_txt(self, txt, color=BLACK):
		color_table = { 'LASTHIT': GREEN, 'DENY': YELLOW, 'FAIL': RED }
		color =  color_table[txt] if txt in color_table else BLACK
		text = font.render(txt, True, color, WHITE)
		text_rect = text.get_rect()

		x, y = self.rectc_midpoint()
		text_rect.center = (x, y)

		NOTIFICATIONS.append((text, text_rect))

	def draw(self, surface):

		if self.hp == 0:
			return

		surface.blit(*self.debug_idx_txt())

		self.healthbar.draw(surface)

		self.image = self.animator.get_image()
		surface.blit(self.image, self.rect)

		#pg.draw.rect(surface, (135,0,0), self.rect, 3)
		#pg.draw.rect(surface, (0,0,135), self.rectc, 1)
		#pg.draw.rect(surface, (135,135,135), self.rectc3, 1)

	def move(self):
		self.rect.move_ip(0,10)
		if (self.rect.bottom > 600):
			self.rect.top = 0
			self.rect.center = (random.randint(30, 370), 0)

	def update(self, surface):

		if self.hp == 0:
			return

		self.set_facing_direction()
		self.walk_to_target()

		"""
		pressed_keys = pg.key.get_pressed()

		would_collide = lambda x,y: any([pg.Rect.colliderect(self.rectc.move(x,y), other.rectc) for other in ALL[DIRE]])
		
		if self.rect.left > 0 and pressed_keys[K_LEFT] and not would_collide(-5,0):
			self.rect.move_ip(-5, 0)
			self.animator.set_state('walk')
		elif self.rect.right < 640 and pressed_keys[K_RIGHT] and not would_collide(5,0):
			self.rect.move_ip(5, 0)
			self.animator.set_state('walk')
		elif pressed_keys[K_RETURN]:
			self.animator.set_state('attack')
		else:
			self.animator.set_state('idle')			
		"""

	#def set_target(self, target):
	#	self.target = target

	def set_facing_direction(self):
		if not self.target: return True
		self.animator.face_east = True if self.rect.left < self.target.rect.left else False

def get_random_points(Xs, Ys, margin, count=4):
	Ps = []
	while len(Ps) != count:
		x = random.randint(Xs[0], Xs[1])
		y = random.randint(Ys[0], Ys[1])

		if not any([((x - p[0])**2 + (y - p[1])**2) <= margin**2 for p in Ps]):
			Ps.append((x,y))

	return Ps

def refresh_map(others_):
	global MAP
	MAP = np.zeros((640,480), dtype=np.int)

	others = [ (p.rectc3, p.id) for p in others_ ]

	for (m, pid) in others:
		MAP[m.left : m.left+m.width+1, m.top : m.top+m.height+1] = pid

def sort_for_render(players):
	return sorted(players, key=lambda p: (p.rect.top, p.rect.left))

def setup_pg():
	pg.init()
	global font, surface, FramePerSec

	# The screen/display has to be initialized before you can load an image.
	surface = pg.display.set_mode((640, 480))

	pg.display.set_caption('Last hit simulator')

	FramePerSec = pg.time.Clock()
	font = pg.font.Font('freesansbold.ttf', 12)

def update_notifications():
	for idx, (text, text_rect) in enumerate(NOTIFICATIONS):
		text_rect.move_ip(0, -5)
		if text_rect.top < 0:
			NOTIFICATIONS.pop(idx)

def render_scene(creeps, players, force_realtime=False):
	surface.fill(WHITE)

	for p in sort_for_render(creeps):
		p.update(surface)

	for p in sort_for_render(creeps + players):
		p.draw(surface)

	# render NOTIFICATIONS
	update_notifications()
	for text, text_rect in NOTIFICATIONS:
		surface.blit(text, text_rect)

	pg.display.update()

	if force_realtime:
		FramePerSec.tick(30)

def main():
	print ("STARTING MAIN....")
	setup_pg()

	RADIANT_COUNT = 4
	DIRE_COUNT = 1

	radiant_players, dire_players = [], []
	radiant_points, dire_points = [], []

	# [(100,100),(100,400),(100,250)]:
	# [(100,100),(100,200)]:
	# [(80,221), (129,84), (189, 212), (246, 94)]: # viewfield
	for x, y in get_random_points((100,300), (100,300), 100, RADIANT_COUNT): 
		radiant_points.append((x,y))
		p = Player((x, y), 0)
		radiant_players.append(p)
		ALL[RADIANT].add(p)		

	# [(400,200)]:
	# [(384, 261), (420, 138)]: # viewfield
	for x, y in get_random_points((350,550), (100,300), 100, DIRE_COUNT):
		dire_points.append((x,y))
		p = Player((x, y), 1)		
		dire_players.append(p)
		ALL[DIRE].add(p)

	for idx, (x_p, y_p) in enumerate(radiant_points):
		chosen = np.array([ ((x_p-x_t)**2 + (y_p-y_t)**2) for (x_t, y_t) in dire_points ]).argmin()
		radiant_players[idx].set_target(dire_players[chosen])
			
	for idx, (x_p, y_p) in enumerate(dire_points):
		chosen = np.array([ ((x_p-x_t)**2 + (y_p-y_t)**2) for (x_t, y_t) in radiant_points ]).argmin()
		dire_players[idx].set_target(radiant_players[chosen])

	# for debug, set ID
	for idx, p in enumerate(radiant_players):
		radiant_players[idx].id = idx + 1
	# for debug, set ID
	for idx, p in enumerate(dire_players):
		dire_players[idx].id = idx + len(radiant_players) + 1

	while True:
		for e in pg.event.get():
			pass

		screen.fill(WHITE)

		refresh_map(radiant_players + dire_players)
		for p in sort_for_render(dire_players):
			p.draw(screen)
		for p in sort_for_render(radiant_players):
			p.draw(screen)

		pg.display.update()

		FramePerSec.tick(FPS)


if __name__ == "__main__":
	main()

