import pickle

chats = pickle.load(open('../data/tech/chats.pickle', 'rb'))

print('\n')

def leave_only_text(message):
    '''
    Leave only text in message with images
    '''
    if message is None:
        return None, False
    try:
        message_copy = message.copy()
        # Check if there is images in message
        trimmed = False
        if 'content' in message_copy and type(message_copy['content']) == list:
            # Leave only text in message
            for i in range(len(message_copy['content'])):
                if message_copy['content'][i]['type'] == 'text':
                    message_copy['content'] = message_copy['content'][i]['text']
                    trimmed = True
                    break
        return message_copy, trimmed
    except Exception as e:
        print('Error in leave_only_text: ', e)
        return None, False

for userid in chats.keys():
    print('***', str(userid), '***')
    for message in chats[userid]:
        text, trimmed = leave_only_text(message)
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

print('Statistics:\n====================================')
print('         Total ($): ', round(total, 2))
print('====================================')
print('         Users: ', len(stats.keys()))
print('====================================')
