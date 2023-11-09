import pickle

chats = pickle.load(open('./data/tech/chats.pickle', 'rb'))

print('\n')

for userid in chats.keys():
    print('*************', str(userid), '*************')
    for message in chats[userid]:
        print(message)
    print('*************************************', '\n\n')

stats = pickle.load(open('./data/tech/stats.pickle', 'rb'))

total = 0
rating = []
total_tokens = {}
for userid in stats.keys():
    total += stats[userid]['Tokens used']/1000*0.0015
    total += stats[userid]['Speech2text seconds']/60*0.006
    rating.append(stats[userid]['Tokens used'])
    total_tokens[stats[userid]['Tokens used']] = userid

print('\n')

print('\n====================================')
print('         Total ($): ', round(total, 3))
print('====================================')
print('         Users: ', len(stats.keys()))
print('====================================')
