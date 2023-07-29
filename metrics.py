#!/usr/bin/env python3
'''
Script to calculate metrics for the chatbot
Metrics include:
    - Total number of users
    - Total number of tokens used
    - Total number of seconds spent on speech2text
    - Total cost of the chatbot in USD
    - Average number of messages per user per last hour (from rate limit)
    - Cost per user
'''
import pickle
import time

chats = pickle.load(open('./data/tech/chats.pickle', 'rb'))
stats = pickle.load(open('./data/tech/stats.pickle', 'rb'))
rates = pickle.load(open('./data/tech/ratelimit.pickle', 'rb'))

# Calculate total cost of chatbot
total_cost = 0
for userid in stats.keys():
    total_cost += stats[userid]['Prompt tokens used'] / 1000 * 0.0015
    total_cost += stats[userid]['Completion tokens used']/   1000 * 0.002
    total_cost += stats[userid]['Speech2text seconds'] / 60 * 0.006
total_cost = round(total_cost, 3)

# Calculate total number of users
total_users = len(chats.keys())

# Calculate total number of tokens used
total_tokens_prompt = 0
total_tokens_completion = 0
for userid in stats.keys():
    total_tokens_prompt += stats[userid]['Prompt tokens used']
    total_tokens_completion += stats[userid]['Completion tokens used']

# Calculate total number of seconds spent on speech2text
total_speech2text = 0
for userid in stats.keys():
    total_speech2text += stats[userid]['Speech2text seconds']

# Calculate average number of messages per user per last hour
total_messages_last_hour = 0
total_users_last_hour = 0
for userid in rates.keys():
    used = False
    for t in rates[userid]:
        if time.time() - t <= 3600:
            total_messages_last_hour += 1
            used = True
    if used:
        total_users_last_hour += 1

if total_users_last_hour == 0:
    average_messages_last_hour = 'n/a'
else:
    average_messages_last_hour = round(total_messages_last_hour / total_users_last_hour, 3)

# Calculate cost per user
cost_per_user = round(total_cost / total_users, 3)

# toal lines in whitelist.txt
total_whitelist = 0
with open('./data/whitelist.txt', 'r') as f:
    for line in f:
        total_whitelist += 1

# total lines in log (./logs/common.log)
total_log = {
    'DEBUG': 0,
    'INFO': 0,
    'WARNING': 0,
    'ERROR': 0,
    'CRITICAL': 0,
    'exception': 0,
    'total': 0
}
with open('./logs/common.log', 'r') as f:
    for line in f:
        if ' - DEBUG - ' in line:
            total_log['DEBUG'] += 1
        elif ' - INFO - ' in line:
            total_log['INFO'] += 1
        elif ' - WARNING - ' in line:
            total_log['WARNING'] += 1
        elif ' - ERROR - ' in line:
            total_log['ERROR'] += 1
        elif ' - CRITICAL - ' in line:
            total_log['CRITICAL'] += 1
        elif 'EXCEPTION' in line:
            total_log['exception'] += 1
        else:
            pass
        total_log['total'] += 1
        

# Print metrics
print('\n===== Chatbot metrics =====')
print('  * Users (with history): ', total_users)
print('  * Users (whitelist): ', total_whitelist)
print('  * Users (last hour): ', total_users_last_hour)
print('  -----')
print('  * Total ($): ', total_cost)
print('  * Cost per user ($): ', cost_per_user)
print('  -----')
print('  * Tokens used (prompt): ', total_tokens_prompt)
print('  * Tokens used (completion): ', total_tokens_completion)
print('  * Voice seconds: ', total_speech2text)
print('  -----')
print('  * Average messages per user (last hour): ', average_messages_last_hour)

print('\n===== Log metrics =====')
print('  * DEBUG: ', total_log['DEBUG'])
print('  * INFO: ', total_log['INFO'])
print('  * WARNING: ', total_log['WARNING'])
print('  * ERROR: ', total_log['ERROR'])
print('  * CRITICAL: ', total_log['CRITICAL'])
print('  * Exception: ', total_log['exception'])
print('  -----')
print('  * Total lines: ', total_log['total'])
