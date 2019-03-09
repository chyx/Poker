import sys
sys.path.append('/usr/lib/virtualbox/')
import virtualbox
import subprocess
from PIL import Image
import time
from configobj import ConfigObj
import numpy as np
import logging


class VirtualBoxController(virtualbox.library.IMouse):
    def __init__(self):
        self.logger = logging.getLogger('vm_control')
        # self.logger = logging.getLogger()

        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.DEBUG)
        # self.logger.addHandler(handler)

        self.logger.setLevel(logging.DEBUG)
        try:
            self.vbox = virtualbox.VirtualBox()
            list = self.get_vbox_list()
            config = ConfigObj("config.ini")
            self.control_name = config['control']
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
                # self.vm = self.vbox.find_machine(self.control_name)
                self.vm = self.vbox.machines[0]
                self.session = self.vm.create_session()
        except Exception as e:
            self.logger.warning(str(e))

    def get_vbox_list(self):
        vm_list = [vm.name for vm in self.vbox.machines]
        return vm_list

    def get_screenshot_vbox(self):
        h, w, _, _, _, _ = self.session.console.display.get_screen_resolution(0)
        subprocess.call(["VBoxManage", "controlvm", "poker", "screenshotpng", "screenshot_vbox.png"])
        return Image.open('screenshot_vbox.png')

    def mouse_move_vbox(self, x, y, dz=0, dw=0):
        self.session.console.mouse.put_mouse_event_absolute(x, y, dz, dw, 0)

    def mouse_click_vbox(self, x, y, dz=0, dw=0):
        self.session.console.mouse.put_mouse_event_absolute(x, y, dz, dw, 0b1)
        time.sleep(np.random.uniform(0.27, 0.4, 1)[0])
        self.session.console.mouse.put_mouse_event_absolute(x, y, dz, dw, 0)

    def get_mouse_position_vbox(self):
        x = self.session.console.mouse.pointer_shape.hot_x
        y = self.session.console.mouse.pointer_shape.hot_y
        return x, y


if __name__ == '__main__':
    vb = VirtualBoxController()
    list = vb.get_vbox_list()

    vb.start_vm()
    vb.mouse_click_vbox(50, 50)
    x, y = vb.get_mouse_position_vbox()
    print(x, y)

    vb.mouse_move_vbox(1,1)
    # vb.mouse_click_vbox(1,1)
    vb.get_screenshot_vbox()
    h, w = 1280, 720
