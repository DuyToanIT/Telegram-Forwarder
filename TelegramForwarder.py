import asyncio
import os
import traceback
import urllib
from dotenv import load_dotenv

import requests
from telethon import events
from telethon.sync import TelegramClient
import pandas as pd

load_dotenv()
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
SOURCE_IDS = os.getenv("SOURCE_IDS")
CSV_FILE = os.getenv("CSV_FILE")


def export_message(sender, chat_title, message_text, message_time):
    # Prepare data to log
    data = {
        'Sender': [sender],
        'Channel': [chat_title],
        'Message': [message_text],
        'Timestamp': [message_time]
    }

    # Create a DataFrame
    df = pd.DataFrame(data)

    # Check if the CSV file exists
    if os.path.exists(CSV_FILE):
        # Append to existing CSV
        df.to_csv(CSV_FILE, mode='a', header=False, index=False, encoding='utf-8-sig')
    else:
        # Create new CSV
        df.to_csv(CSV_FILE, mode='w', header=True, index=False, encoding='utf-8-sig')
    print("Write data done...")


class TelegramForwarder:
    def __init__(self, api_id, api_hash, phone_number):
        self.api_id = api_id
        self.api_hash = api_hash
        self.phone_number = phone_number
        self.client = TelegramClient('session_' + phone_number, api_id, api_hash)

    async def list_chats(self):
        await self.client.connect()

        # Ensure you're authorized
        if not await self.client.is_user_authorized():
            await self.client.send_code_request(self.phone_number)
            await self.client.sign_in(self.phone_number, input('Enter the code: '))

        # Get a list of all the dialogs (chats)
        dialogs = await self.client.get_dialogs()
        with open(f"chats_of_{self.phone_number}.txt", "w") as chats_file:
            for dialog in dialogs:
                title = dialog.title.encode("utf-8")
                print(f"Chat ID: {dialog.id}, Title: {title}")
                chats_file.write(f"Chat ID: {dialog.id}, Title: {urllib.parse.quote(title.decode('utf-8'))} \n")

        print("List of groups printed successfully!")

    async def forward_messages_to_channel(self, source_chat_ids, destination_channel_id, keywords):
        await self.client.connect()

        if not await self.client.is_user_authorized():
            await self.client.send_code_request(self.phone_number)
            await self.client.sign_in(self.phone_number, input('Enter the code: '))

        async def process_chat(source_chat_id):
            last_message_id = (await self.client.get_messages(source_chat_id, limit=1))[0].id

            while True:
                print(f"Checking messages in chat {source_chat_id} and forwarding them...")
                messages = await self.client.get_messages(source_chat_id, min_id=last_message_id, limit=None)

                for message in reversed(messages):
                    if keywords:
                        if message.text and any(keyword in message.text.lower() for keyword in keywords):
                            print(f"Message contains a keyword in chat {source_chat_id}: {message.text}")
                            await self.client.send_message(destination_channel_id, message.text)
                            print("Message forwarded")
                    else:
                        await self.client.send_message(destination_channel_id, message.text)
                        print("Message forwarded")

                    last_message_id = max(last_message_id, message.id)

                await asyncio.sleep(5)

        tasks = [process_chat(chat_id) for chat_id in source_chat_ids]
        await asyncio.gather(*tasks)

    async def forward_messages_to_google_sheet(self, source_chat_ids):
        await self.client.connect()

        if not await self.client.is_user_authorized():
            await self.client.send_code_request(self.phone_number)
            await self.client.sign_in(self.phone_number, input('Enter the code: '))

        @self.client.on(events.NewMessage(chats=source_chat_ids))
        async def handler(event):
            message_text = event.message.message
            chat_title = (await event.get_chat()).title
            message_time = event.message.date.strftime('%Y-%m-%d %H:%M:%S')
            # Encode the message and chat title
            encoded_message = urllib.parse.quote(message_text.decode('utf-8'))
            encoded_chat_title = urllib.parse.quote(chat_title.decode('utf-8'))

            url = f"{WEBHOOK_URL}?chat_name={encoded_chat_title}&message={encoded_message}&timestamp={message_time}"

            try:
                response = requests.get(url)
                data = response.json()

                if data.get('status') == 'success':
                    print('Message forwarded successfully to Google Sheets.')
                else:
                    print('Failed to forward the message to Google Sheets.')
            except requests.exceptions.RequestException as e:
                print(
                    f'An error occurred while trying to forward the message from "{chat_title}" to Google Sheets:')
                print(e)
                print(traceback.format_exc())

        print("Listening for new messages...")
        await self.client.run_until_disconnected()

    async def forward_messages_to_csv(self, source_chat_ids):
        await self.client.connect()

        if not await self.client.is_user_authorized():
            await self.client.send_code_request(self.phone_number)
            await self.client.sign_in(self.phone_number, input('Enter the code: '))

        @self.client.on(events.NewMessage(chats=source_chat_ids))
        async def handler(event):
            message_text = event.message.message
            chat_title = (await event.get_chat()).title
            message_time = event.message.date.strftime('%Y-%m-%d %H:%M:%S')
            sender = event.message.sender_id

            # Log to CSV
            export_message(sender, chat_title, message_text, message_time)

        print("Listening for new messages...")
        await self.client.run_until_disconnected()


def read_credentials():
    try:
        with open("credentials.txt", "r") as file:
            lines = file.readlines()
            api_id = lines[0].strip()
            api_hash = lines[1].strip()
            phone_number = lines[2].strip()
            return api_id, api_hash, phone_number
    except FileNotFoundError:
        print("Credentials file not found.")
        return None, None, None

def write_credentials(api_id, api_hash, phone_number):
    with open("credentials.txt", "w") as file:
        file.write(api_id + "\n")
        file.write(api_hash + "\n")
        file.write(phone_number + "\n")




async def main():
    api_id, api_hash, phone_number = read_credentials()

    if api_id is None or api_hash is None or phone_number is None:
        api_id = input("Enter your API ID: ")
        api_hash = input("Enter your API Hash: ")
        phone_number = input("Enter your phone number: ")
        write_credentials(api_id, api_hash, phone_number)

    forwarder = TelegramForwarder(api_id, api_hash, phone_number)

    print("Choose an option:")
    print("1. List Chats")
    print("2. Forward Messages by input")
    print("3. Forward Messages Default")
    print("4. Forward Messages to GG Sheet")
    print("5. Forward Messages to file csv")

    choice = input("Enter your choice: ")

    if choice == "1":
        await forwarder.list_chats()
    elif choice == "2":
        source_chat_ids = list(map(int, input("Enter the source chat IDs (comma-separated): ").split(",")))
        destination_channel_id = int(input("Enter the destination chat ID: "))
        print("Enter keywords if you want to forward messages with specific keywords, or leave blank to forward every message!")
        keywords = input("Put keywords (comma-separated if multiple, or leave blank): ").split(",")
        await forwarder.forward_messages_to_channel(source_chat_ids, destination_channel_id, keywords)

    elif choice == "3":
        source_chat_ids = [-4225744802, -4255186558, -1001744966356, -1001349387323, -1001307184953]
        destination_channel_id = -1002240352332
        keywords = ""
        await forwarder.forward_messages_to_channel(source_chat_ids, destination_channel_id, keywords)

    elif choice == "4":
        source_chat_ids = list(map(int, SOURCE_IDS.split(',')))
        await forwarder.forward_messages_to_google_sheet(source_chat_ids)

    elif choice == "5":
        source_chat_ids = list(map(int, SOURCE_IDS.split(',')))
        await forwarder.forward_messages_to_csv(source_chat_ids)

    else:
        print("Invalid choice")

if __name__ == "__main__":
    asyncio.run(main())
