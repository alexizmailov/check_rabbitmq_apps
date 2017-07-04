#!/usr/bin/python
# Author: Izmaylov Alexey
# Company: Infoxchange
# 
import urllib2, base64, json, argparse, platform

class col:
    OK = '\033[92m'
    WARN = '\033[93m'
    CRIT = '\033[91m'
    RESET = '\033[0m'

NAGIOS = False

LOCATION = platform.node().split("-")[0] # int, pm

parser = argparse.ArgumentParser(description="RabbitMQ app checker")
parser.add_argument('-H', help='IP addresses (comma separated)')
parser.add_argument('--authfile', help='authfile for rabbitmq')
parser.add_argument('--user', help='username for rabbitmq')
parser.add_argument('--passwd', help='password for rabbitmq')
parser.add_argument('--nagios', action='store_true', help='formatted output for nagios')
parser.add_argument('--warn', help='Warning threshold (100K by default)')
parser.add_argument('--crit', help='Critical threshold (200K by default)')
parser.add_argument('--strip', help='Remove patterns from vhost names (Should be comma separated list, no spaces)')
args = parser.parse_args()

if args.nagios: # If not - it's manual run and output will be colorized table view instead of single line
  NAGIOS = True

MQ_USER = ''
MQ_PASS = ''

if args.authfile:
  try:
    authfile = open(args.authfile)
    creds = {}
    for line in authfile.readlines():
      values = line.split("=", 1)
      creds[values[0]] = values[1].strip()
    MQ_USER = creds['username']
    MQ_PASS = creds['password']
  except:
    print "Error setting credentials from auth file"
elif args.user and args.passwd:
  MQ_USER = args.user
  MQ_PASS = args.passwd
else:
  print "No credentials provided"

if args.H:
  NODE_LIST = args.H.split(",")
elif LOCATION=='int':
  NODE_LIST = ['10.51.60.71','10.51.60.72'] # default IPs for INT when this check is run manually
else:
  NODE_LIST = ['10.52.60.71','10.52.60.72'] # default IPs for PM

TOTAL_WARN   = 300000
TOTAL_CRIT   = 500000

APP_WARN = 100000
APP_CRIT = 200000

WARN_LIST = ['','']
CRIT_LIST = ['','']

EXIT_CODE = 0
EXIT_MSG = ''
strip_this = ''

if args.warn:
  APP_WARN = int(args.warn)
if args.crit:
  APP_CRIT = int(args.crit)

if args.strip:
  strip_this = args.strip.split(",")

PERFORMANCE_DATA = [{}, {}]



def get_data(REQUEST, NODE):
  API_BASE = 'http://%s:15672/api/' % (NODE)
  API_REQUEST = "%s%s" % (API_BASE, REQUEST)

  password_mgr = urllib2.HTTPPasswordMgrWithDefaultRealm()
  request = urllib2.Request(API_REQUEST)
  base64string = base64.encodestring('%s:%s' % (MQ_USER, MQ_PASS)).replace('\n', '')
  request.add_header("Authorization", "Basic %s" % base64string)
  try:
    response = urllib2.urlopen(request, timeout=5)
  except:
    return -1
  data = response.read()
  return json.loads(data)



NODE_NUMBER = -1
NODE_DOWN_MSG = ''
NODE_DOWN = []

for NODE in NODE_LIST:
  TOTAL_MSG = 0
  NODE_NUMBER += 1

  REQUEST = 'vhosts'
  result = get_data(REQUEST, NODE)

  if result == -1:
    NODE_DOWN.append(True)
    NODE_DOWN_MSG += "%s-mq-0%d IS DOWN(!!). " % (LOCATION, (NODE_NUMBER + 1 ))
  else:
    NODE_DOWN.append(False)

    vhost_list = []
    vhost_number = len(result)

    for vhost in range(0,vhost_number):
      if not ('/' in result[vhost]['name']
        or '/mcollective' in result[vhost]['name']
        or 'nagios' in result[vhost]['name']
        or 'flower' in result[vhost]['name']):

        vhost_list.append(result[vhost]['name'])

        if 'messages' in result[vhost].keys():
          if result[vhost]['messages'] > APP_CRIT:
            CRIT_LIST[NODE_NUMBER] += "%s(!!) " % result[vhost]['name']
            EXIT_CODE = 2
          elif result[vhost]['messages'] > APP_WARN:
            WARN_LIST[NODE_NUMBER] += "%s(!) " % result[vhost]['name']
            if EXIT_CODE != 2:
              EXIT_CODE = 1

    for vhost in vhost_list:
      REQUEST = 'queues/%s' % vhost
      result = get_data(REQUEST, NODE)

      celeryev_msgs = 0

      if strip_this:
        for strip_line in strip_this:
          vhost = vhost.replace(strip_line, '')
          CRIT_LIST[NODE_NUMBER] = CRIT_LIST[NODE_NUMBER].replace(strip_line, '') # Save space on dashbord by removing '_docker_dev' and '_infoxchangeapps_net_au'
          WARN_LIST[NODE_NUMBER] = WARN_LIST[NODE_NUMBER].replace(strip_line, '')
      PERFORMANCE_DATA[NODE_NUMBER][vhost]={}

      for q_num in range(0,len(result)):
        if not 'celery.pidbox' in result[q_num]['name']:
          if 'celeryev.' in result[q_num]['name']:
            celeryev_msgs += int(result[q_num]['messages'])
          else:
            PERFORMANCE_DATA[NODE_NUMBER][vhost][result[q_num]['name']] = result[q_num]['messages']
            TOTAL_MSG += result[q_num]['messages']
        PERFORMANCE_DATA[NODE_NUMBER][vhost]['ev'] = celeryev_msgs
      TOTAL_MSG += celeryev_msgs

# If both nodes are up - compare their data
if not NODE_DOWN_MSG:
  ERROR_COUNT = 0

  if PERFORMANCE_DATA[0] != PERFORMANCE_DATA[1]:
    for vhost in PERFORMANCE_DATA[0]:
      if PERFORMANCE_DATA[0][vhost] != PERFORMANCE_DATA[1][vhost]:
        ERROR_COUNT += 1
    if ERROR_COUNT > 2:
      EXIT_MSG = "Split brain (!!). Run this check manually in terminal"
      EXIT_CODE = 2


if NAGIOS:
  if NODE_DOWN[0] and NODE_DOWN[1]:
    print "Both nodes are down (!!)"
    exit(2)
  elif NODE_DOWN[0]:
    ALIVE_NODE = 1
  else:
    ALIVE_NODE = 0

# total number of message
  total_tag = ''
  if TOTAL_MSG > TOTAL_CRIT:
    EXIT_CODE = 2
    total_tag = '(!!)'
  elif TOTAL_MSG > TOTAL_WARN:
    EXIT_CODE = 1
    total_tag = '(!)'

  total_msg = '%d msg in total%s. '  % ( TOTAL_MSG, total_tag )

#messages per app
  app_msg = ''
  for vhost, data in PERFORMANCE_DATA[ALIVE_NODE].iteritems():
    if sum(data.values()) > APP_CRIT:
      app_msg += "%s(!!)" % vhost
    elif sum(data.values()) > APP_WARN:
      app_msg += "%s(!)" % vhost
  if app_msg == '':
    app_msg = ' All apps are ok'

# performance output
  perf_output = '|'
  for key, value in PERFORMANCE_DATA[ALIVE_NODE].iteritems():
    if value:
      main_queue = value.keys()[0]
      ceev_queue = value.keys()[1]
      perf_output += " {0}_{1}={2} {0}_ev={3}".format(key, main_queue, value[main_queue], value[ceev_queue])

  EXIT_MSG = "%s%s%s%s" % (NODE_DOWN_MSG, total_msg, app_msg, perf_output)
  print EXIT_MSG
  exit(EXIT_CODE)


# ============= MANUAL =============
else:
  for key in PERFORMANCE_DATA[0].keys():
    if (PERFORMANCE_DATA[0][key] == PERFORMANCE_DATA[1][key]):
      output_line = "{}synced:{} {:40}".format(col.OK, col.RESET, key)
      for queue, msgs in PERFORMANCE_DATA[0][key].iteritems():
        if msgs > APP_CRIT:
          COLOR = col.CRIT
        elif msgs > APP_WARN:
          COLOR = col.WARN
        else:
          COLOR = col.RESET
        output_line += "    %s%s = %s%s" %(COLOR, queue, msgs, col.RESET)
      print output_line

    else:
      print "%s%s%s - splitbrain:" % (col.CRIT, key, col.RESET)
      print "%s-mq-03" % LOCATION
      for queue, msgs in PERFORMANCE_DATA[0][key].iteritems():
        print "   %s = %s " % (queue, msgs)
      print "%s-mq-04" % LOCATION
      for queue, msgs in PERFORMANCE_DATA[1][key].iteritems():
        print "   %s=%s " % (queue, msgs)

