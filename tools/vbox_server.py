import virtualbox
from PIL import Image
import time
import base64
from configobj import ConfigObj
import numpy as np
import logging
import sys
from flask import Flask
from jsonrpc import JSONRPCResponseManager, dispatcher
from werkzeug.wrappers import Request, Response
from werkzeug.serving import run_simple


class VirtualBoxController(virtualbox.library.IMouse):
    def __init__(self):
        self.logger = logging.getLogger('vm_control')
        self.logger.setLevel(logging.DEBUG)
        try:
            self.vbox = virtualbox.VirtualBox()
            list = self.get_vbox_list()
            config = ConfigObj("config.ini")
            # self.control_name = config['control']
            self.control_name = 'uk'
            if self.control_name not in list:
                self.control_name = 'Direct mouse control'
                config['control'] = 'Direct mouse control'
                config.write()
            self.start_vm()
            self.logger.debug("VM session established successfully")

        except Exception as e:
            self.logger.error(str(e))

    def start_vm(self):
        try:
            if self.control_name != 'Direct mouse control':
                self.vm = self.vbox.find_machine(self.control_name)
                self.session = self.vm.create_session()
        except Exception as e:
            self.logger.warning(str(e))

    def get_vbox_list(self):
        vm_list = [vm.name for vm in self.vbox.machines]
        return vm_list

    def get_screenshot_vbox(self):
        h, w, _, _, _, _ = self.session.console.display.get_screen_resolution(0)
        return self.session.console.display.take_screen_shot_to_array(0, h, w, virtualbox.library.BitmapFormat.png)

    def mouse_move_vbox(self, x, y, dz=0, dw=0):
        self.session.console.mouse.put_mouse_event_absolute(x, y, dz, dw, 0)

    def mouse_click_vbox(self, x, y, dz=0, dw=0):
        self.session.console.mouse.put_mouse_event_absolute(x, y, dz, dw, 0b1)
        time.sleep(np.random.uniform(0.27, 0.4, 1)[0])
        self.session.console.mouse.put_mouse_event_absolute(x, y, dz, dw, 0)

    def get_mouse_position_vbox(self):
        # todo: not working
        x = self.session.console.mouse_pointer_shape.hot_x()
        y = self.session.console.mouse_pointer_shape.hot_y()
        return x, y


@Request.application
def application(request):
    response = JSONRPCResponseManager.handle(
            request.data, dispatcher)
    return Response(response.json, mimetype='application/json')


if __name__ == '__main__':
    logging.basicConfig(stream=sys.stdout)
    vb = VirtualBoxController()
    dispatcher['start_vm'] = vb.start_vm
    dispatcher['get_screenshot_vbox'] = vb.get_screenshot_vbox
    dispatcher['get_vbox_list'] = vb.get_vbox_list
    dispatcher['get_screenshot_vbox'] = lambda: base64.b64encode(vb.get_screenshot_vbox())
    run_simple('localhost', 4001, application)
