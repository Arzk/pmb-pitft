# -*- coding: utf-8 -*-
import time
import logging
import os
import glob
from threading import Thread
import subprocess
from mpd import MPDClient
import pylast
import config

class MPDControl:
	def __init__(self):

		self.logger = logging.getLogger("PiTFT-Playerui.MPD")
		self.coverartThread = None

		self.mpdc = None
		self.noConnection = False
		# Pylast
		self.lfm_connected = False

		# MPD Client
		self.connect()
		
		if self.mpdc:
			self.logger.info("MPD server version: %s" % self.mpdc.mpd_version)

		# Capabilities
		self.capabilities = {}
		self.capabilities["name"]            = "mpd"
		self.capabilities["connected"]       = False
		self.capabilities["volume_enabled"]  = config.volume_enabled
		self.capabilities["seek_enabled"]    = True
		self.capabilities["random_enabled"]  = True 
		self.capabilities["repeat_enabled"]  = True
		self.capabilities["elapsed_enabled"] = True
		self.capabilities["library_enabled"] = False

		# Things to remember
		self.data = {}
		self.data["status"] = {}
		self.data["status"]["state"]     = ""
		self.data["status"]["elapsed"]   = ""
		self.data["status"]["repeat"]    = ""
		self.data["status"]["random"]    = ""
		self.data["status"]["volume"]    = ""
                                      
		self.data["song"]  = {}         
		self.data["song"]["artist"]      = ""
		self.data["song"]["album"]       = ""
		self.data["song"]["date"]        = ""
		self.data["song"]["track"]       = ""
		self.data["song"]["title"]       = ""
		self.data["song"]["time"]        = ""
                                      
		self.data["cover"]               = False
		self.data["coverartfile"]        = ""
                                      
		self.data["update"] = {}         
		self.data["update"]["active"]    = False
		self.data["update"]["state"]     = False
		self.data["update"]["elapsed"]   = False
		self.data["update"]["random"]    = False
		self.data["update"]["repeat"]    = False
		self.data["update"]["volume"]    = False
		self.data["update"]["trackinfo"] = False
		self.data["update"]["coverart"]  = False

						
	def __getitem__(self, item):
		return self.data[item]
		
	def __call__(self, item):
		return self.capabilities[item]

	def refresh(self, active=False):
		status = {}
		song = {}
		if not self.mpdc:
			self.connect()
		else:
			try:
				status = self.mpdc.status()
				# Check for changes in status
				if status != self.data["status"]:
					if status["state"] != self.data["status"]["state"]:
						self.data["update"]["state"] = True
						# Started playing - request active status
						if status["state"] == "play":
							self.data["update"]["active"] = True
					if status["repeat"] != self.data["status"]["repeat"]:
						self.data["update"]["repeat"]  = True
					if status["random"] != self.data["status"]["random"]:
						self.data["update"]["random"]  = True
					if status["volume"] != self.data["status"]["volume"]:
						self.data["update"]["volume"]  = True
					if status["state"] != "stop":
						if status["elapsed"] != self.data["status"]["elapsed"]:
							self.data["update"]["elapsed"] = True
					else:
						status["elapsed"] = ""
						
					# Save new status
					self.data["status"] = status
	
			except Exception as e:
				self.logger.debug(e)
				self.mpdc = None
				if not self.noConnection:
					self.logger.info("Lost connection to MPD server")
	
			try:
				# Fetch song info 
				if active:
					song = self.mpdc.currentsong()
					
					# Sanity check
					if "artist" not in song:
						song["artist"] = ""
						
					if "album" not in song:
						song["album"] = ""
						
					if "date" not in song:
						song["date"] = ""
						
					if "track" not in song:
						song["track"] = ""
						
					if "title" not in song:
						song["title"] = ""

					if "time" not in song:
						song["time"] = ""

					# Fetch coverart
					if self.data["song"]["album"] != song["album"]:
						self.logger.debug("MPD coverart changed, fetching...")
						self.data["cover"] = False
		
						# Find cover art on different thread
						try:
							if self.coverartThread:
								if not self.coverartThread.is_alive():
									self.coverartThread = Thread(target=self.fetch_coverart(song))
									self.coverartThread.start()
							else:
								self.coverartThread = Thread(target=self.fetch_coverart(song))
								self.coverartThread.start()
						except Exception, e:
							self.logger.debug("Coverartthread: %s" % e)			
					
					# Check for changes in song
					if song != self.data["song"]:
						if (
								song["artist"] != self.data["song"]["artist"] or
								song["album"]  != self.data["song"]["album"]  or
								song["date"]   != self.data["song"]["date"]   or
								song["track"]  != self.data["song"]["track"]  or
								song["title"]  != self.data["song"]["title"]  or
								song["time"]   != self.data["song"]["time"]
						):
							self.data["update"]["trackinfo"] = True
						if song["album"] != self.data["song"]["album"]:
							self.data["update"]["coverart"] = True
						if song["time"] != self.data["song"]["time"]:
							self.data["update"]["elapsed"] = True
		
						# Save new song info
						self.data["song"] = song
			except Exception as e:
				self.logger.debug(e)
				self.mpdc = None
				if not self.noConnection:
					self.logger.info("Lost connection to MPD server")

	def force_update (self,item="all"):
		if item == "all":
			self.data["update"] = dict.fromkeys(self.data["update"], True)
		else:
			self.data["update"][item] = True

	def update_ack(self, updated):
		self.data["update"][updated] = False
		
	def connect(self):
		if not self.noConnection:
			self.logger.info("Trying to connect to MPD server")

		client = MPDClient()
		client.timeout = 10
		client.idletimeout = None
		if not self.mpdc:
			 try:
				client.connect(config.mpd_host, config.mpd_port)
				self.mpdc = client
				self.logger.info("Connection to MPD server established.")
				self.noConnection = False
			 except Exception, e:
				self.noConnection = True
				if not self.noConnection:
					self.logger.info(e)
				self.mpdc = None

		# (re)connect to last.fm
		if not self.lfm_connected and config.API_KEY and config.API_SECRET:
			self.connect_lfm()

	def disconnect(self):
		# Close MPD connection
		if self.mpdc:
			self.mpdc.close()
			self.mpdc.disconnect()
			self.logger.debug("Disconnected from MPD")

	# Direction: +, -
	def set_volume(self, volume):
		self.mpdc.control("volume", volume)

	def control(self, command, parameter=-1):
		try:
			if command == "next":
				self.mpdc.next()
			elif command == "previous":
				self.mpdc.previous()
			elif command == "pause":
				self.mpdc.pause()
			elif command == "play":
				self.mpdc.play()
			elif command == "stop":
				self.mpdc.stop()
			elif command == "rwd":
				self.mpdc.seekcur("-10")
			elif command == "ff":
				self.mpdc.seekcur("+10")
			elif command == "seek" and parameter != -1:
				seektime = parameter*float(self.data["song"]["time"])
				self.mpdc.seekcur(seektime)
			elif command == "repeat":
				repeat = (int(self.data["status"]["repeat"]) + 1) % 2
				self.mpdc.repeat(repeat)
			elif command == "random":
				random = (int(self.data["status"]["random"]) + 1) % 2
				self.mpdc.random(random)
			elif command == "volume" and parameter != -1:
				self.mpdc.setvol(parameter)
		except Exception, e:
			self.logger.info(e)
			self.mpdc = None
			if not self.noConnection:
				self.logger.info("Lost connection to MPD server")

	def load_playlist(self, command):
		try:
			self.mpdc.clear()
			self.mpdc.load(command)
		except Exception, e:
			self.logger.info(e)
			self.mpdc = None
			if not self.noConnection:
				self.logger.info("Lost connection to MPD server")

	def get_playlists(self):
		try:
			return self.mpdc.listplaylists()
		except Exception, e:
			self.logger.info(e)
			self.mpdc = None
			if not self.noConnection:
				self.logger.info("Lost connection to MPD server")

	def get_playlist(self):
		try:
			return self.mpdc.playlistinfo()
		except Exception, e:
			self.logger.info(e)
			self.mpdc = None
			if not self.noConnection:
				self.logger.info("Lost connection to MPD server")

	def play_item(self, number):
		try:
			self.mpdc.play(number)
		except Exception, e:
			self.logger.info(e)
			self.mpdc = None
			if not self.noConnection:
				self.logger.info("Lost connection to MPD server")

	def fetch_coverart(self, song):
		self.data["cover"] = False
		self.data["coverartfile"]=""

		# Search for local coverart
		if "file" in song and config.library_path:

			folder = os.path.dirname(config.library_path + "/" + song["file"])
			coverartfile = ""

			# Get all folder.* files from album folder
			coverartfiles = glob.glob(folder + '/folder.*')

			if coverartfiles:
				self.logger.debug("Found coverart files: %s" % coverartfiles)
				# If multiple found, select one of them
				for file in coverartfiles:
					if file.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
						if not coverartfile:
							coverartfile = file
							self.logger.debug("Set coverart: %s" % coverartfile)
						else:
							# Found multiple files. Assume that the largest one has the best quality
							if os.path.getsize(coverartfile) < os.path.getsize(file):
								coverartfile = file
								self.logger.debug("Better coverart: %s" % coverartfile)
				if coverartfile:
					# Image found, load it
					self.logger.debug("Using MPD coverart: %s" % coverartfile)
					self.data["coverartfile"] = coverartfile
					self.data["cover"] = True
					self.data["update"]["coverart"]	= True
				else:
					self.logger.debug("No local coverart file found, switching to Last.FM")

		# No existing coverart, try to fetch from LastFM
		if not self.data["cover"] and self.lfm_connected:

			try:
				lastfm_album = self.lfm.get_album(song["artist"], song["album"])
			except Exception, e:
				self.lfm_connected = False
				lastfm_album = {}
				self.logger.exception(e)
				pass

			if lastfm_album:
				try:
					coverart_url = lastfm_album.get_cover_image(2)
					if coverart_url:
						self.data["coverartfile"] = "/dev/shm/mpd_cover.png"
						subprocess.check_output("wget -q %s -O %s" % (coverart_url, self.data["coverartfile"]), shell=True )
						self.logger.debug("MPD coverart downloaded from Last.fm")
						self.data["cover"] = True
						self.data["update"]["coverart"]	= True
				except Exception, e:
					self.logger.exception(e)
					pass

	def connect_lfm(self):
		self.logger.info("Setting Pylast")
		username = config.username
		password_hash = pylast.md5(config.password_hash)
		self.lfm_connected = False
		try:
			self.lfm = pylast.LastFMNetwork(api_key = config.API_KEY, api_secret = config.API_SECRET)
			self.lfm_connected = True
			self.logger.debug("Connected to Last.fm")
		except:
			self.lfm = ""
			time.sleep(5)
			self.logger.debug("Last.fm not connected")