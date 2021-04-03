#!/home/ola/telegram_bot/.telegram/bin/python3
# -*- coding: utf-8 -*-

import subprocess, shlex, logging
from functools import wraps
import time

from picamera import PiCamera

from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

from secrets import *

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

def capture_img(res="high"):
    W = 3280
    H = 2464
    if res == "medium":
        W = 1640
        H = 1232
    elseif res == "low":
        W = 640
        H = 480
    
    camera = PiCamera()
    camera.resolution = (W, H)
    camera.start_preview()
    # Camera warm-up time
    time.sleep(2)
    name = datetime.now().strftime("%Y%m%d-%H%M%S-%f.jpg")
    path = "images/" + name
    camera.capture(path)
    return path
    
@restricted
def get_img(update, context):
    path = capture_img()
    context.bot.send_photo(chat_id=update.effective_chat.id, open(path,'rb'))

def main() -> None:
    # Create the Updater and pass it your bot's token.
    updater = Updater(token=TOKEN, use_context=True)
    dispatcher = updater.dispatcher
    dispatcher.add_handler(CommandHandler('ip', get_ip))
    dispatcher.add_handler(CommandHandler('bilde', get_img))

    #dispatcher.add_error_handler(error_handler)

    # Start the Bot
    updater.start_polling()

    # Run the bot until the user presses Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT
    updater.idle()


if __name__ == '__main__':
    main()
