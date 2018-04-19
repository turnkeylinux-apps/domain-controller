# Copyright (c) 2010 Alon Swartz <alon@turnkeylinux.org>

import re
import sys
import dialog
import traceback
from StringIO import StringIO

email_re = re.compile(r"(?:^|\s).*\S@\S+(?:\s|$)", re.IGNORECASE)

class Error(Exception):
    pass

def password_complexity(password):
    """return password complexity score from 0 (invalid) to 4 (strong)"""

    lowercase = re.search('[a-z]', password) is not None
    uppercase = re.search('[A-Z]', password) is not None
    number = re.search('\d', password) is not None
    nonalpha = re.search('\W', password) is not None

    return sum([lowercase, uppercase, number, nonalpha])

class Dialog:
    def __init__(self, title, width=60, height=20):
        self.width = width
        self.height = height

        self.console = dialog.Dialog(dialog="dialog")
        self.console.add_persistent_args(["--no-collapse"])
        self.console.add_persistent_args(["--backtitle", title])

    def _handle_exitcode(self, retcode):
        if retcode == 2: # ESC, ALT+?
            text = "Do you really want to quit?"
            if self.console.yesno(text) == 0:
                sys.exit(0)
            return False
        return True

    def _calc_height(self, text):
        height = 6
        for line in text.splitlines():
            height += (len(line) / self.width) + 1

        return height

    def wrapper(self, dialog_name, text, *args, **kws):
        try:
            method = getattr(self.console, dialog_name)
        except AttributeError:
            raise Error("dialog not supported: " + dialog_name)

        while 1:
            try:
                ret = method("\n" + text, *args, **kws)
                if type(ret) is int:
                    retcode = ret
                else:
                    retcode = ret[0]

                if self._handle_exitcode(retcode):
                    break

            except Exception:
                sio = StringIO()
                traceback.print_exc(file=sio)

                self.msgbox("Caught exception", sio.getvalue())

        return ret

    def error(self, text):
        height = self._calc_height(text)
        return self.wrapper("msgbox", text, height, self.width, title="Error")

    def msgbox(self, title, text):
        height = self._calc_height(text)
        return self.wrapper("msgbox", text, height, self.width, title=title)

    def infobox(self, text):
        height = self._calc_height(text)
        return self.wrapper("infobox", text, height, self.width)

    def inputbox(self, title, text, init='', ok_label="OK", cancel_label="Cancel"):
        height = self._calc_height(text) + 3
        no_cancel = True if cancel_label == "" else False
        return self.wrapper("inputbox", text, height, self.width, title=title,
                            init=init, ok_label=ok_label, cancel_label=cancel_label,
                            no_cancel=no_cancel)

    def yesno(self, title, text, yes_label="Yes", no_label="No"):
        height = self._calc_height(text)
        retcode = self.wrapper("yesno", text, height, self.width, title=title,
                               yes_label=yes_label, no_label=no_label)

        return True if retcode is 0 else False

    def menu(self, title, text, choices):
        """choices: array of tuples
            [ (opt1, opt1_text), (opt2, opt2_text) ]
        """
        retcode, choice = self.wrapper("menu", text, self.height, self.width,
                                       menu_height=len(choices)+1,
                                       title=title, choices=choices,
                                       no_cancel=True)
        return choice

    def get_password(self, title, text, pass_req=8, min_complexity=3):
	req_string = '\n\nPassword Requirements\n - must be atleast %d characters long\n - must not contain parentheses\n - must contain characters from at least %d of the following catagories: uppercase, lowercase, numbers, symbols' % (pass_req, min_complexity)
        def ask(title, text):
            return self.wrapper('passwordbox', text+req_string, title=title,
                                ok_label='OK', no_cancel='True', height = self._calc_height(text+req_string)+3)[1]

        while 1:
            password = ask(title, text)
            if not password:
                self.error("Please enter non-empty password!")
                continue

            if isinstance(pass_req, int):
                if len(password) < pass_req:
                    self.error("Password must be at least %s characters." % pass_req)
                    continue
            else:
                if not re.match(pass_req, password):
                    self.error("Password does not match complexity requirements.")
                    continue

            if password_complexity(password) < min_complexity:
                self.error("Insecure password! Mix uppercase, lowercase, and at least one number. Multiple words and punctuation are highly recommended but not strictly required.")
                continue

            parentheses = re.search('[\(\)]', password) is not None

            if parentheses:
                self.error("Please do not use parentheses in a password, as it breaks Samba.")
                continue

            if password == ask(title, 'Confirm password'):
                return password

            self.error('Password mismatch, please try again.')

    def get_email(self, title, text, init=''):
        while 1:
            email = self.inputbox(title, text, init, "Apply", "")[1]
            if not email:
                self.error('Email is required.')
                continue

            if not email_re.match(email):
                self.error('Email is not valid')
                continue

            return email

    def get_input(self, title, text, init=''):
        while 1:
            s = self.inputbox(title, text, init, "Apply", "")[1]
            if not s:
                self.error('%s is required.' % title)
                continue

            return s

