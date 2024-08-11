from misc import leave_only_text
import pickle
import asyncio

chats = pickle.load(open('../data/tech/chats.pickle', 'rb'))

print('\n')

for userid in chats.keys():
    print('***', str(userid), '***')
    for message in chats[userid]:
        text, trimmed = asyncio.run(leave_only_text(message))
        if trimmed:
            text['content'] += ' (IMAGE DELETED IN OUTPUT)'
        print(text)
    print('****************', '\n')

stats = pickle.load(open('../data/tech/stats.pickle', 'rb'))

total = 0
rating = []
total_tokens = {}
for userid in stats.keys():
    cost = 0
    cost += stats[userid]['Prompt tokens used'] / 1000 * 0.01 if 'Prompt tokens used' in stats[userid] else 0
    cost += stats[userid]['Completion tokens used'] / 1000 * 0.03 if 'Completion tokens used' in stats[userid] else 0
    cost += stats[userid]['Images generated'] * 0.04 if 'Images generated' in stats[userid] else 0
    total += stats[userid]['Speech2text seconds'] / 60 * 0.006 if 'Speech2text seconds' in stats[userid] else 0
    cost += stats[userid]['Speech to text seconds'] / 60 * 0.006 if 'Speech to text seconds' in stats[userid] else 0
    print(f'User {userid} spent around ${round(cost, 2)}')
    rating.append((userid, round(cost, 3)))
    total += cost

print('\n====================================')
print('         Total ($): ', round(total, 2))
print('====================================')
print('         Users: ', len(stats.keys()))
print('====================================')
