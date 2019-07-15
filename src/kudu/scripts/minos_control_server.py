#! /usr/bin/env python
# coding=utf-8

# A tool for restarting servers, typically to restart tservers in kudu cluster

import sys
import commands
import time
import json
import re
import os

master_rpcs = ''        # master rpc addresses
cluster = ''            # cluster name in minos config
job = 'tablet_server'   # job name in minos config
operate = 'stop'        # minos operate type, currently support: restart, stop, rolling_update
tasks = range(0, 5)     # an int element list, e.g. '[n]' for a single node, or 'range(m, n)' for several nodes
flags = ''              # minos flags, e.g. '--update_config' for updating config
known_unhealth_nodes = set()
#known_unhealth_nodes.add()    # it's ok to add some known unhealth nodes, e.g. some already stoped servers

def get_minos_type(cluster_name):
    minos_type = 'null'
    minos_clinet_path = None

    minos_config_file = os.getenv('MINOS_CONFIG_FILE')
    minos_clinet_dir = os.getenv('MINOS_CLIENT_DIR')
    if minos_config_file is not None and minos_clinet_dir is not None:
        minos_config_dir = os.path.dirname(minos_config_file)
        minos_config = '%s/xiaomi-config/conf/kudu/kudu-%s.cfg' % (minos_config_dir, cluster_name)
        if os.path.exists(minos_config) and os.path.exists(minos_clinet_dir + '/deploy'):
            return 'minos1.0', minos_clinet_dir
    
    minos2_config_file = os.getenv('MINOS2_CONFIG_FILE')
    minos2_clinet_dir = os.getenv('MINOS2_CLIENT_DIR')
    if minos2_config_file is not None and minos2_clinet_dir is not None:
        minos2_config_dir = os.path.dirname(minos2_config_file)
        minos2_config = '%s/xiaomi-config/conf/kudu/kudu-%s.yaml' % (minos2_config_dir, cluster_name)
        if os.path.exists(minos2_config) and os.path.exists(minos2_clinet_dir + '/deploy'):
            return 'minos2.0', minos2_clinet_dir

    return minos_type, minos_clinet_path

def get_host(host_port):
    return host_port.split(':')[0]

def is_cluster_health():
    status, output = commands.getstatusoutput('${KUDU_HOME}/kudu cluster ksck @%s -consensus=false'
                                              ' -ksck_format=json_compact -color=never'
                                              ' -sections=MASTER_SUMMARIES,TSERVER_SUMMARIES,TABLE_SUMMARIES'
                                              ' 2>/dev/null'
                                              % master_rpcs)
    unhealth_nodes = set()
    if status == 0 or status == 256:
        ksck_info = json.loads(output)
        for master in ksck_info['master_summaries']:
            if master['health'] != 'HEALTHY':
                unhealth_nodes.add(get_host(master['address']))
        for tserver in ksck_info['tserver_summaries']:
            if tserver['health'] != 'HEALTHY':
                unhealth_nodes.add(get_host(tserver['address']))
        if 'table_summaries' in ksck_info:
            for table in ksck_info['table_summaries']:
                if table['health'] != 'HEALTHY':
                    unhealth_nodes.add(table['name'])
    else:
        unhealth_nodes.add('mockone')

    return unhealth_nodes


def check_parameter(message, parameter, allow_empty = False):
    print(message % parameter)
    answer = sys.stdin.readline().strip('\n').lower()
    if answer != 'y' and answer != '':
        exit()
    if (not allow_empty and
        (not parameter or
         (isinstance(parameter, list) and len(parameter) == 0) or
         (isinstance(parameter, str) and parameter.strip() == ''))):
        print(time_header() + 'You should provide a valid parameter')
        exit()


def wait_cluster_health():
    print(time_header() + 'Wait cluster to be health ...')
    nodes = is_cluster_health()
    health = (len(nodes) == 0)
    while not health:
        health = True
        for node in nodes:
            if node not in known_unhealth_nodes:
                health = False
                print(time_header() + 'Unhealthy node: ' + node)
                time.sleep(5)
                nodes = is_cluster_health()
                break


def parse_node_from_minos_output(output):
    host = ''
    regex = re.compile('Stop task [0-9]+ of (tablet_server) on ([0-9a-z-.]+)\(0\).+')
    match = regex.search(output)
    if match is not None:
        host = match.group(2)
    return host


def time_header():
    return time.strftime("%Y-%m-%d %H:%M:%S ", time.localtime())


check_parameter('You will operate on cluster: %s? (y/n)', cluster)
minos_type, minos_client_path = get_minos_type(cluster)
if minos_type == 'null' or minos_client_path is None:
    print("You should set these environment variables:\n* MINOS_CONFIG_FILE\n* MINOS_CLIENT_DIR\n" +
          "* MINOS2_CONFIG_FILE\n* MINOS2_CLIENT_DIR\nand check cluster name")
    exit()
check_parameter('The minos type is: %s? (y/n)', minos_type)
check_parameter('The minos client path is: %s? (y/n)', minos_client_path)
check_parameter('The master rpc addresses are: %s? (y/n)', master_rpcs)
check_parameter('You will operate on job: %s? (y/n)', job)
check_parameter('You will operate on tasks: %s? (y/n)', tasks)
check_parameter('The operate is: %s? (y/n)', operate)
if operate == 'rolling_update' and flags.find('--update_package') == -1:
    flags += ' --update_package'
    if minos_type == 'minos2.0' and flags.find('--confirm_install') == -1:
        flags += ' --confirm_install'
check_parameter('The extra flags are: %s? (y/n)', flags, True)
check_parameter('The known unhealth nodes are: %s? (y/n)', ','.join(known_unhealth_nodes), True)

wait_cluster_health()
for task in tasks:
    if not isinstance(task, int):
        print(time_header() + '%s is not a valid integer task id' % str(task))
        exit()

    print(time_header() + 'Start to operate on task %d' % task)
    cmd = ('%s/deploy %s kudu %s --job %s --task %d --skip_confirm %s'
          % (minos_client_path, operate, cluster, job, task, flags))
    print(cmd)
    status, output = commands.getstatusoutput(cmd)
    print(time_header() + 'operate status: ' + str(status))
    print(output)
    if operate == 'stop':
        known_unhealth_nodes.add(parse_node_from_minos_output(output))

    wait_cluster_health()

    print(time_header() + '==========================')
    time.sleep(10)

print(time_header() + 'Complete sucessfully')
