import requests
import json
import base64
import time
from PIL import Image

class VirtualBoxController():
    def __init__(self):
        self.url = "http://localhost:4001/jsonrpc"
        self.headers = {'content-type': 'application/json'}
        return

    def _send_rpc(self, name, **kwargs):
        payload = {
                "method": name,
                "params": kwargs,
                "jsonrpc": "2.0",
                "id": 0,
                }
        return requests.post(
                self.url, data=json.dumps(payload),
                headers=self.headers).json()['result']


    def start_vm(self):
        self._send_rpc('start_vm')

    def get_vbox_list(self):
        return self._send_rpc('get_vbox_list')

    def get_screenshot_vbox(self):
        png = base64.b64decode(self._send_rpc('get_screenshot_vbox'))
        open('screenshot_vbox.png', 'wb').write(png)
        # image=Image.fromarray(png)
        # image.show()
        time.sleep(0.5)
        return Image.open('screenshot_vbox.png')

    def mouse_move_vbox(self, x, y, dz=0, dw=0):
        return

    def mouse_click_vbox(self, x, y, dz=0, dw=0):
        return

    def get_mouse_position_vbox(self):
        return


def main():
    vb = VirtualBoxController()
    vb.get_vbox_list()
    vb.get_screenshot_vbox()

    payload = {
            "method": "get_vbox_list",
            "params": [],
            "jsonrpc": "2.0",
            "id": 0,
            }
    response = requests.post(
            url, data=json.dumps(payload), headers=headers).json()
    response
