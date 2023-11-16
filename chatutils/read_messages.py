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
    total += stats[userid]['Tokens used']/1000*0.0015
    total += stats[userid]['Speech2text seconds']/60*0.006
    rating.append(stats[userid]['Tokens used'])
    total_tokens[stats[userid]['Tokens used']] = userid

print('Statistics:\n====================================')
print('         Total ($): ', round(total, 3))
print('====================================')
print('         Users: ', len(stats.keys()))
print('====================================')
