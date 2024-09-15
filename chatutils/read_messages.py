from .misc import leave_only_text
import pickle
from .datatypes import Message
chats = pickle.load(open('./data/tech/chats.pickle', 'rb'))

print('\n')

for userid in chats.keys():
    print('***', str(userid), '***')
    for message in chats[userid]:
        m = message.to_dict(text_only=True)
        print(m)
    print('****************', '\n')
