from flask import Flask
from flask import request
from flask import jsonify
from threading import Timer
from inspect import signature
import threading
from pywidevine.cdm import Cdm
from pywidevine.device import Device
from pywidevine.pssh import PSSH
import argparse
import time
import os
import socket
import signal
import requests

parser = argparse.ArgumentParser(description='command', formatter_class=argparse.RawTextHelpFormatter)
parser.add_argument('--autoClose', '-c', help='是否自动关闭，默认为300s，设置为0则不自动关闭',default='300')
parser.add_argument('--port', '-p', help='设置端口号')
args = parser.parse_args()
args.autoClose=int(args.autoClose)

cdmInstance=None

app = Flask(__name__)
PID = os.getpid()

@app.route("/ping",methods=["GET"])
def ping():
    print('run ping')
    closeServer()
    return jsonify(status="success")

@app.route("/close",methods=["GET"])
def close():
    shutdown()
    return jsonify(status="success")

def debounce(wait):
    def decorator(fn):
        sig = signature(fn)
        caller = {}

        def debounced(*args, **kwargs):
            nonlocal caller

            try:
                bound_args = sig.bind(*args, **kwargs)
                bound_args.apply_defaults()
                called_args = fn.__name__ + str(dict(bound_args.arguments))
            except:
                called_args = ''

            t_ = time.time()

            def call_it(key):
                try:
                    # always remove on call
                    caller.pop(key)
                except:
                    pass

                fn(*args, **kwargs)

            try:
                # Always try to cancel timer
                caller[called_args].cancel()
            except:
                pass

            caller[called_args] = Timer(wait, call_it, [called_args])
            caller[called_args].start()

        return debounced

    return decorator


@app.route("/loadDevice",methods=["POST"])
def loadDevice():
    global cdmInstance
    form = request.form
    device=None
    try:
        device = Device.load(form.get("path"))
    except:
        return jsonify(status="error")
    cdmInstance = Cdm.from_device(device)
    return jsonify(status="success")


@app.route("/getKeys",methods=["POST"])
def getKeys():
    form = request.form
    license_url = form.get("url")
    headers= form.get("headers")
    pssh= form.get("pssh")
    pssh_value = PSSH(pssh)
    cdm_session_id = cdmInstance.open()
    challenge = cdmInstance.get_license_challenge(cdm_session_id, pssh_value)
    licence = requests.post(
        license_url, data=challenge
    )
    licence.raise_for_status()
    cdmInstance.parse_license(cdm_session_id, licence.content)
    keys = []
    for key in cdmInstance.get_keys(cdm_session_id):
        if "CONTENT" in key.type:
            keys.append({
                "kid":key.kid.hex,
                "key":key.key.hex()
            })
    cdmInstance.close(cdm_session_id)
    return jsonify(status="success",data=keys)


def shutdown():
    if args.autoClose==0:
        return
    print('自动销毁')
    os._exit(1)

@debounce(args.autoClose)
def closeServer():
    shutdown()


@app.errorhandler(Exception)
def framework_error(e):
    print(e)
    return jsonify(status="error")

if __name__ == '__main__':
    if args.port==None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(('localhost', 0))
        args.port = sock.getsockname()[1]
        sock.close() 
    closeServer()
    app.run(host='0.0.0.0')
