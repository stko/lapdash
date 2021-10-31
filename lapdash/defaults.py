#!/usr/bin/env python
# -*- coding: utf-8 -*-

CONFIG_FILE = 'config/config.json'
USER_DATA_FILE = 'config/users.json'
WEB_ROOT_DIR = '../web/'

# Message through the Websocket channel
MSG_SOCKET_CONNECT = 'wsconnect'
MSG_SOCKET_CLOSE = 'wsclose'
MSG_SOCKET_MSG = 'wsmsg'
MSG_SOCKET_WRITESTRING = 'WRITESTRING'
MSG_SOCKET_WSCONNECT = 'WSCONNECT'
MSG_SOCKET_BROWSER = "BROWSER"
# old re-used OOBD Message identifier

CM_VISUALIZE = "VISUALIZE"
CM_PAGE = "PAGE"
CM_CHANNEL = "CHANNEL"
CM_PAGEDONE = "PAGEDONE"
CM_VALUE = "VALUE"
CM_UPDATE = "UPDATE"
CM_RES_BUS = "RESULT_BUS"
CM_RES_LOOKUP = "RESULT_LOOKUP"
CM_BUSTEST = "BUSTEST"
CM_WRITESTRING = "WRITESTRING"
CM_DBLOOKUP = "DBLOOKUP"
CM_PARAM = "PARAM"
CM_DIALOG_INFO = "DIALOG_INFO"
CM_IOINPUT = "IOINPUT"

#
EPA_LOADDIR = "EPA_LOADDIR"