#!/home/ola/telegram_bot/.telegram/bin/python3
# -*- coding: utf-8 -*-

import subprocess, shlex, logging, os, time, json, asyncio, binascii
from functools import wraps
from datetime import datetime

from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

from secrets import *

with open("config.json", "r") as config:
    CONFIG = json.load(config)

PI = CONFIG.get("pi")
CAMERA = CONFIG.get("camera")
GPIO = CONFIG.get("gpio")
MQTT = CONFIG.get("mqtt")

if CAMERA:
    from picamera import PiCamera

if MQTT:
    import paho.mqtt.client as mqtt
    MQTT_HOST = CONFIG.get("mqtt_host")
    MQTT_PORT = CONFIG.get("mqtt_port", 1883)

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                     level=logging.INFO, )

logger = logging.getLogger(__name__)

def error_handler(update: object, context: CallbackContext) -> None:
    """Log the error and send a telegram message to notify the developer."""
    # Log the error before we do anything else, so we can see it even if something breaks.
    logger.error(msg="Exception while handling an update:", exc_info=context.error)

    # traceback.format_exception returns the usual python message about an exception, but as a
    # list of strings rather than a single string, so we have to join them together.
    tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
    tb_string = ''.join(tb_list)

    # Build the message with some markup and additional information about what happened.
    # You might need to add some logic to deal with messages longer than the 4096 character limit.
    update_str = update.to_dict() if isinstance(update, Update) else str(update)
    message = (
        f'An exception was raised while handling an update\n'
        f'<pre>update = {html.escape(json.dumps(update_str, indent=2, ensure_ascii=False))}'
        '</pre>\n\n'
        f'<pre>context.chat_data = {html.escape(str(context.chat_data))}</pre>\n\n'
        f'<pre>context.user_data = {html.escape(str(context.user_data))}</pre>\n\n'
        f'<pre>{html.escape(tb_string)}</pre>'
    )

    # Finally, send the message
    context.bot.send_message(chat_id=DEVELOPER_CHAT_ID, text=message, parse_mode=ParseMode.HTML)


def restricted(func):
    @wraps(func)
    def wrapped(update, context, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id not in LIST_OF_ADMINS:
            print("Unauthorized access denied for {}.".format(user_id))
            return
        return func(update, context, *args, **kwargs)
    return wrapped

@restricted
def echo(update: Update, context: CallbackContext) -> None:
    """Echo the user message."""
    update.message.reply_text(update.message.text)

def on_message(client, userdata, msg):
    msg.payload = msg.payload.decode("UTF-8")
    bot = userdata.get("bot")
    topics = userdata.get("mqtt_topics")
    topic_actions = topics.get(msg.topic, None)
    if not topic_actions:
        print(f"no topic actions for {msg.topic}")
        return
    if msg.payload != topic_actions.get("trigger", None):
        return
    else:
        telegram_actions = topic_actions.get("telegram_actions", None)
        if telegram_actions:
            for action in telegram_actions:
                globals()[action](bot, msg, topic_actions)

def send_image(bot, msg, *args):
    if CAMERA:
        path = capture_img()
        bot.send_message(chat_id=DEVELOPER_CHAT_ID, text=f"Sender bilde...")
        bot.send_photo(DEVELOPER_CHAT_ID, open(path,"rb"))
    else:
        bot.send_message(chat_id=DEVELOPER_CHAT_ID, text="Could not capture image, camera not configured.")

def send_message(bot, msg, topic_actions):
    message = topic_actions.get("message", msg.payload)
    bot.send_message(chat_id=DEVELOPER_CHAT_ID, text=f"{msg.topic}: {message}")

def get_local_ip():
    text = subprocess.check_output(['ifconfig', 'wlan0']).decode("ASCII").split(" ")
    index = text.index("inet")
    local_ip = text[index+1]
    return(local_ip)

def get_global_ip():
    cmd = "curl ifconfig.me"
    process = subprocess.Popen(shlex.split(cmd), stdout=subprocess.PIPE)
    output, error = process.communicate()
    global_ip = output.decode("ASCII")
    return(global_ip)

@restricted
def get_ip(update, context):
    local_ip = get_local_ip()
    global_ip = get_global_ip()
    context.bot.send_message(chat_id=update.effective_chat.id, text=f"Global ip: {global_ip}\nLocal ip: {local_ip}")

def get_pub_state():
    f = open("states/pub_state.txt", "r")
    state = f.read().strip()
    f.close()
    if state in ["0", "1"]:
        return state
    else:
        set_pub_state("1")
        return "1"

def set_pub_state(state):
    f = open("states/pub_state.txt", "w")
    f.write(str(state))

def callback_heartbeats(context):
    """Send heartbeat, message if error"""
    job = context.job
    command = "bash /home/ola/telegram_bot/heartbeat_pub.sh 192.168.0.5"
    process = subprocess.Popen(command.split(), stdout=subprocess.PIPE)
    output, error = process.communicate()
    print("output: ", output)
    state = get_pub_state()
    if (output.decode("ascii").strip() == "1") and (state == "0"):
        context.bot.send_message(job.context, text="MQTT server back online")
        set_pub_state(1)
    elif (output.decode("ascii").strip() == "0") and (state == "1"):
        context.bot.send_message(job.context, text="MQTT server offline")
        set_pub_state(0)

@restricted
def heartbeats(update, context):
    print("heartbeats")
    context.bot.send_message(chat_id=update.effective_chat.id,
                      text="Starting heartbeat monitoring")
    context.job_queue.run_repeating(callback_heartbeats, 60, context=update.effective_chat.id)


def capture_img(res="high"):
    """
    Mulig Pi zero ikke håndterer full oppløsnin(3280x2464)
    Bedre å teste dette når jeg er på hytta
    """
    W = 3280
    H = 2464
    if res == "medium":
        W = 1640
        H = 1232
    elif res == "low":
        W = 640
        H = 480

    camera = PiCamera()
    camera.resolution = (W, H)
    camera.start_preview()
    # Camera warm-up time
    time.sleep(2)
    name = datetime.now().strftime("%Y%m%d-%H%M%S-%f.jpg")
    dirname = os.path.dirname(__file__)
    path = os.path.join(dirname, "images", name)
    camera.capture(path)
    camera.close()
    return path

@restricted
def get_img(update, context):
    context.bot.send_message(chat_id=update.effective_chat.id, text=f"Tar bilde...")
    path = capture_img()
    context.bot.send_message(chat_id=update.effective_chat.id, text=f"Sender bilde...")
    context.bot.send_photo(update.effective_chat.id, open(path,"rb"))

def main() -> None:
    # Create the Updater and pass it your bot's token.
    updater = Updater(token=TOKEN, use_context=True)
    dispatcher = updater.dispatcher
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, echo))
    
    if PI:
        dispatcher.add_handler(CommandHandler('ip', get_ip))
    dispatcher.add_handler(CommandHandler('heartbeats', heartbeats))
    #dispatcher.add_handler(CommandHandler('stop', stop_heartbeats, pass_job_queue=True))

    if CAMERA:
        dispatcher.add_handler(CommandHandler('bilde', get_img))

    #dispatcher.add_error_handler(error_handler)

    # Start the Bot
    updater.start_polling()

    if MQTT:
        # Start MQTT
        userdata = {"bot": updater.bot, "mqtt_topics": CONFIG.get("mqtt_topics")}
        client = mqtt.Client("Python", userdata=userdata)
        #client.on_connect = on_connect
        client.on_message = on_message
        client.connect(MQTT_HOST, MQTT_PORT, 60)
        client.loop_start()
        for topic in CONFIG.get("mqtt_topics").keys():
            client.subscribe(topic)
    
    # Run the bot until the user presses Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT
    updater.idle()


if __name__ == '__main__':
    main()
