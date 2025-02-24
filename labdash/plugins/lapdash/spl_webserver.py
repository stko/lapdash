#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys
import os
import json
from base64 import b64encode
import argparse
import time
import webbrowser

import socket

from labdash.jsonstorage import JsonStorage
from flask import Flask, render_template, send_from_directory, request
from werkzeug.datastructures import Headers
from flask_sockets import Sockets, Rule
from gevent import pywsgi
from geventwebsocket.handler import WebSocketHandler

from pprint import pprint

from io import StringIO
from labdash.splthread import SplThread
from labdash import defaults


# own local modules


class WebsocketUser:
	'''handles all user related data
	'''

	def __init__(self, name, ws):
		self.name = name
		self.ws = ws


class SplPlugin(SplThread):
	plugin_id = 'webserver'
	plugin_names = ['Flask Webserver']

	def __init__(self, modref):
		''' creates the HTTP and websocket server
		'''

		self.modref = modref
		self.program_dir = os.path.dirname(__file__)
		super().__init__(modref.message_handler, self)
		# reads the config, if any
		self.config = JsonStorage('webserver', 'backup', "config.json",
			{
				'server_config': {
					"credentials": "",
					"host": "0.0.0.0",
					"port": 8000,
					"secure": False,
					"openbrowser" : True
				},
				'actual_settings': {
					'theme':'default',
					'www_root_dir': os.path.realpath(os.path.join(self.program_dir,'../../../web/')),
					'epa_root_dir': [os.path.realpath(os.path.join(self.program_dir,'../../../web/examples/'))],
					'eol_root_dir': [os.path.realpath(os.path.join(self.program_dir,'../../../web/eol/'))]
				}

			})
		server_config = self.config.read("server_config", {})
		# set up the argument parser with values from the config
		parser = argparse.ArgumentParser()
		parser.add_argument("--host", default=server_config["host"],
							help="the IP interface to bound the server to")
		parser.add_argument("-p", "--port", default=server_config["port"],
							help="the server port")
		parser.add_argument("-s", "--secure", action="store_true", default=server_config["secure"],
							help="use secure https: and wss:")
		parser.add_argument("-c", "--credentials",  default=server_config["credentials"],
							help="user credentials")
		parser.add_argument("-b", "--browser", action="store_true", default=server_config["openbrowser"],
							help="opens a browser window")
		self.args = parser.parse_args()
		self.theme=self.config.read('actual_settings')['theme']
		self.app = Flask('webserver')
		self.sockets = Sockets(self.app)
		self.ws_clients = []  # my actual browser connections
		self.actual_file_id=None
		self.epa_catalog_xml_string = None
		self.eol_catalog_xml_string = None
		self.awaiting_initial_content_list=True
		self.modref.message_handler.add_event_handler(
			'webserver', 0, self.event_listener)
		# https://githubmemory.com/repo/heroku-python/flask-sockets/activity
		self.sockets.url_map.add(
			Rule('/ws', endpoint=self.on_create_ws_socket, websocket=True))

		@self.app.route('/',methods=['GET', 'POST'])
		def index():
			headers=None
			if request.method == 'POST':
				if 'theme' in  request.form:
					self.theme= request.form['theme']

					'''
					Somehow we'll need to tell the Browser to reload all files if the theme has changed - but how?!?!

					headers = Headers()
					headers.add('Content-Type', 'text/plain')
					headers.add('Content-Disposition', 'attachment', filename='foo.png')
					'''

			response = self.app.response_class(
			response=self.epa_catalog_xml_string,
			status=200,
			headers=headers,
			mimetype='application/xml'
			)
			return response

		@self.app.route('/eol/',methods=['GET', 'POST'])
		def init_eol():
			headers=None
			response = self.app.response_class(
			response=self.eol_catalog_xml_string,
			status=200,
			headers=headers,
			mimetype='application/xml'
			)
			return response


		@self.app.route('/eol/<path:path>')
		def handle_eol(path):
			elements=path.split('/') # first we split the path into pieces
			if not elements: # empty path
				return self.app.response_class(
				response="<h2>No EOL reference in URL</h2>",
				status=404
			)
			if not elements[0] in self.eol_directory:
				return self.app.response_class(
					response="<h2>Unknown EOL reference in URL</h2>",
					status=404
				)
			self.actual_file_id=elements[0]
			eol_info=self.eol_directory[elements[0]]
			if len(elements)==1: # this is a request to load a new EOL
				if 'html' in eol_info: # does this package has its own main html page?
					return send_from_directory(eol_info['path'], eol_info['html'])
				else:
					return send_from_directory(os.path.join(self.config.read('actual_settings')['www_root_dir'],'theme',self.theme), 'startpage_eol.html')
						# we serve the file from within an epa directory
			return send_from_directory(eol_info['path'], '/'.join(elements[1:]))
			""" return self.app.response_class(
				response="<h2>Wrong parameters in handle_eol</h2>",
				status=404
			) """

		@self.app.route('/libs/<path:path>')
		def send_libs(path):
			return send_from_directory(os.path.join(self.config.read('actual_settings')['www_root_dir'],'libs'), path)

		@self.app.route('/ld/<path:path>')
		def handle_epa(path):
			elements=path.split('/') # first we split the path into pieces
			if not elements: # empty path
				return self.app.response_class(
				response="<h2>No EPA reference in URL</h2>",
				status=404
			)
			if not elements[0] in self.epa_directory:
				return self.app.response_class(
					response="<h2>Unknown EPA reference in URL</h2>",
					status=404
				)
			self.actual_file_id=elements[0]
			epa_info=self.epa_directory[elements[0]]
			if len(elements)==1: # this is a request to load a new EPA

				if 'html' in epa_info: # does this package has its own main html page?
					return send_from_directory(epa_info['path'], epa_info['html'])
				else:
					return send_from_directory(os.path.join(self.config.read('actual_settings')['www_root_dir'],'theme',self.theme), 'startpage.html')


			# we serve the file from within an epa directory
			return send_from_directory(epa_info['path'], '/'.join(elements[1:]))

		@self.app.route('/theme/<theme>/<path:path>')
		def send_theme(theme,path):
			if theme=='default':
				theme=self.theme
			return send_from_directory(os.path.join(self.config.read('actual_settings')['www_root_dir'],'theme',theme), path)



	def on_create_ws_socket(self, ws):
		''' distributes incoming messages to the registered event handlers

		Args:
			message (:obj:`str`): json string, representing object with 'type' as identifier and 'config' containing the data
		'''
		user=self.find_user_by_ws(ws)
		if user:
			if user != ws:
				self.disconnect()
				user=self.connect(ws)
		else:
			user=self.connect(ws)
		while not ws.closed:
			message = ws.receive()
			if message:
				#self.log_message('websocket received "%s"', str(message))
				try:
					data = json.loads(message)
					self.modref.message_handler.queue_event(
						user.name, defaults.MSG_SOCKET_BROWSER, data)
				except:
					#self.log_message('%s', 'Invalid JSON')
					pass
				#self.log_message('json msg: %s', message)

	def connect(self, ws):
		''' thows a connect event about that new connection
		'''
		#self.log_message('%s', 'websocket connected')
		# this is just a leftover from a previous multi - ws project, but maybe we'll need it again?
		user = WebsocketUser(None, ws)
		self.ws_clients.append(user)
		self.modref.message_handler.queue_event(
			user.name, defaults.MSG_SOCKET_CONNECT, None)
		if self.actual_file_id:
			self.emit(defaults.MSG_SOCKET_WSCONNECT, {'script': 'Python_sim'})
			self.emit('WRITESTRING', {'data': 'bla'})
			self.modref.message_handler.queue_event(
				None, defaults.EPA_LOAD_EPA, self.actual_file_id
			)
			self.modref.message_handler.queue_event(
				None, defaults.EOL_LOAD_EOL, self.actual_file_id
			)


		return user

	def find_user_by_ws(self, ws):
		for user in self.ws_clients:
			if user.ws == ws:
				return user
		return None

	def find_user_by_user_name(self, user_name):
		for user in self.ws_clients:
			if user.name == user_name:
				return user
		return None

	def disconnect(self):
		''' thows a close event about the closed connection
		'''

		user = self.find_user_by_user_name(None)
		if user:
			user.ws.close()
			self.ws_clients.remove(user)
		self.ws = None
		#self.log_message('%s', 'websocket closed')
		self.modref.message_handler.queue_event(
			self.user, defaults.MSG_SOCKET_CLOSE, None)

	def emit(self, type, config):
		''' sends data object as JSON string to websocket client

		Args:
		type (:obj:`str`): string identifier of the contained data type
		config (:obj:`obj`): data object to be sent
		'''

		message = {'type': type, 'config': config}
		user = self.find_user_by_user_name(None)
		pprint(message)
		if user.ws:
			if not user.ws.closed:
				user.ws.send(json.dumps(message))
			else:
				self.ws_clients.remove(user)

	def event_listener(self, queue_event):
		''' checks all incoming queue_events if to be send to one or all users
		'''
		#print("webserver event handler",queue_event.type,queue_event.user)
		if queue_event.type == defaults.MSG_SOCKET_MSG:
			message = {'type': queue_event.data['type'], 'config': queue_event.data['config']}
			json_message=json.dumps(message)
			for user in self.ws_clients:
				if queue_event.user == None or queue_event.user == user.name:
					if not user.ws.closed:
						user.ws.send(json_message)
					else:
						self.ws_clients.remove(user)
			return None  # no futher handling of this event
		if queue_event.type == defaults.EPA_CATALOG:
			self.epa_catalog_xml_string=queue_event.data
			# we need to start the server, if the initial catalog is available
			if self.epa_catalog_xml_string and self.eol_catalog_xml_string and self.awaiting_initial_content_list:
				self.awaiting_initial_content_list=False
			return None  # no futher handling of this event
		if queue_event.type == defaults.EPA_DIRECTORY:
			self.epa_directory=queue_event.data
			return None  # no futher handling of this event
		if queue_event.type == defaults.EOL_CATALOG:
			self.eol_catalog_xml_string=queue_event.data
			# we need to start the server, if the initial catalog is available
			if self.epa_catalog_xml_string and self.eol_catalog_xml_string and self.awaiting_initial_content_list:
				self.awaiting_initial_content_list=False
			return None  # no futher handling of this event
		if queue_event.type == defaults.EOL_DIRECTORY:
			self.eol_directory=queue_event.data
			return None  # no futher handling of this event
		# for further pocessing, do not forget to return the queue event
		return queue_event

	def _run(self):
		''' starts the server
		'''
		try:
			""" 
			origin_dir = os.path.dirname(__file__)
			web_dir = os.path.join(os.path.dirname(
				__file__), defaults.WEB_ROOT_DIR)
			os.chdir(web_dir) """
			'''
			First we prepare the server, but we wait to start until the event message  defaults.EPA_CATALOG comes in
			to gives a valid list of available modules
			'''

			self.server = pywsgi.WSGIServer(
				(self.args.host, self.args.port), self.app, handler_class=WebSocketHandler)
			## read the epa dir with the actual settings
			self.modref.message_handler.queue_event(
				None, defaults.EPA_LOADDIR, {
					'actual_settings': self.config.read('actual_settings')
				}
			)
			## read the eol dir with the actual settings
			self.modref.message_handler.queue_event(
				None, defaults.EOL_LOADDIR, {
					'actual_settings': self.config.read('actual_settings')
				}
			)
			while self.awaiting_initial_content_list:
				time.sleep(0.3)
			if self.args.secure:
				print('initialized secure https server at port %d' %
					(self.args.port))
				webbrowser.open(f'https://{self.extract_ip()}:{self.args.port}', new=2)
			else:
				print('initialized http server at port %d' % (self.args.port))
			if self.args.browser:
				webbrowser.open(f'http://{self.extract_ip()}:{self.args.port}', new=2)

			self.server.serve_forever()

			#os.chdir(origin_dir)
		except KeyboardInterrupt:
			print('^C received, shutting down server')
			self.server.stop()

	def _stop(self):
		self.server.stop()

	def query_handler(self, queue_event, max_result_count):
		''' handler for system queries
		'''
		pass

	# https://www.delftstack.com/de/howto/python/get-ip-address-python/
	def extract_ip(self):
		st = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		try:       
			st.connect(('10.255.255.255', 1))
			IP = st.getsockname()[0]
		except Exception:
			IP = '127.0.0.1'
		finally:
			st.close()
		return IP


if __name__ == '__main__':
	class ModRef:
		store = None
		message_handler = None

	modref = ModRef()
	ws = SplPlugin(modref)
	ws.run()
	while True:
		time.sleep(1)
	ws.stop()
