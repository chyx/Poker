
from PIL import Image, ImageFilter
from configobj import ConfigObj
from decisionmaker.genetic_algorithm import GeneticAlgorithm
from tools.vbox_manager import VirtualBoxController
from tools.mouse_mover import MouseMoverTableBased
from decisionmaker.montecarlo_python import MonteCarlo

import common
import cv2
import json
import pandas
import logging
import numpy as np
import os.path
import pyscreenshot as ImageGrab
import pytesseract
import re
import sys
import time

def get_utg_from_abs_pos(abs_pos, dealer_pos):
  utg_pos = (abs_pos - dealer_pos + 4) % 6
  return utg_pos

def get_abs_from_utg_pos(utg_pos, dealer_pos):
  abs_pos = (utg_pos + dealer_pos - 4) % 6
  return abs_pos


class NewTable(): 
  def __init__(self, bot):
    with open('coords.json') as json_file:  
      self.coords = json.load(json_file)
    self.fakeScreenFilename = 'config_gen/table2.png'
    self.bot = bot

  def TakeFakeScreenshot(self):
    self.screen = common.GetCvImage(self.fakeScreenFilename)

  def TakeScreenshot(self):
    try:
      vb = VirtualBoxController()
      self.screen = cv2.cvtColor(np.array(vb.get_screenshot_vbox()), cv2.COLOR_BGR2RGB)
      self.logger.debug("Screenshot taken from virtual machine")
    except:
      self.logger.warning("No virtual machine found. Press SETUP to re initialize the VM controller")

  def FindTemplate(self, template, threshold=0.1):
    self.TakeFakeScreenshot()
    return common.FindTemplate(self.screen, template, threshold)

  def GetTopLeftCorner(self):
    self.topLeftPos = self.FindTemplate(self.topLeftPattern)

  def CheckButton(self):
    num_points, _, _, _ = common.FindTemplateOnScreen(self.buttonPattern, self.screen, 0.01)
    if num_points < 3: 
      common.RaiseTemplateNotFound('button', self.buttonPattern, self.screen)

  def CheckCheckButton(self):
    try:
      self.FindTemplate(self.checkPattern)
      self.checkButton = True
      self.currentCallValue = 0.0
    except:
      self.checkButton = False

  def CheckCall(self):
    try:
      self.FindTemplate(self.callPattern)
      self.callButton = True
    except:
      self.callButton = False

  def CheckBetbutton(self):
    try:
      self.FindTemplate(self.betRadioPattern)
      self.bet_button_found = True
    except:
      self.bet_button_found = False

  def LoadCards(self, tableType):
    self.card_images = dict()
    card_values = "23456789TJQKA" 
    card_suites = "CDHS"
    for x in card_values:
      for y in card_suites:
        name = "pics/%s/%s%s.png" % (tableType, x, y)
        if not os.path.exists(name):
          self.logger.critical("Card template File not found: " + name)
        self.card_images[x + y.upper()] = common.GetCvImage(name)

    self.topLeftPattern = common.GetCvImage('pics/%s/topleft.png' % tableType)
    self.buttonPattern = common.GetCvImage('pics/%s/button.png' % tableType)
    self.checkPattern = common.GetCvImage('pics/%s/check.png' % tableType)
    self.callPattern = common.GetCvImage('pics/%s/call.png' % tableType)
    self.betRadioPattern = common.GetCvImage('pics/%s/betradio.png' % tableType)
    self.dealerPattern = common.GetCvImage('pics/%s/dealer.png' % tableType)
    self.coveredCardPattern = common.GetCvImage('pics/%s/coveredcard.png' % tableType)

  def GetTableCards(self):
    coord = self.coords['TableCards']
    table_image = self.screen[
        (self.topLeftPos[1] + coord['y1']) : (self.topLeftPos[1] + coord['y2']),
        (self.topLeftPos[0] + coord['x1']) : (self.topLeftPos[0] + coord['x2'])]
    # common.RaiseTemplateNotFound('', table_image, self.screen)

    self.cardsOnTable = []
    for key, card_image in self.card_images.items():
      res = cv2.matchTemplate(table_image, card_image, cv2.TM_SQDIFF_NORMED)
      min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
      if min_val < 0.01:
        self.cardsOnTable.append(key)

    self.gameStage = ''
    if len(self.cardsOnTable) < 1:
      self.gameStage = "PreFlop"
    elif len(self.cardsOnTable) == 3:
      self.gameStage = "Flop"
    elif len(self.cardsOnTable) == 4:
      self.gameStage = "Turn"
    elif len(self.cardsOnTable) == 5:
      self.gameStage = "River"

    if self.gameStage == '':
      self.logger.critical("Table cards not recognised correctly: " + str(len(self.cardsOnTable)))
      self.gameStage = "River"
    return self.cardsOnTable


  def GetDealerPosition(self):
    x, y = self.FindTemplate(self.dealerPattern, 0.01)
    x, y = x - self.topLeftPos[0], y - self.topLeftPos[1]
    coords = self.coords['Dealer']
    self.position_utg_plus = ''
    for n, rect in enumerate(coords, start=0):
      if x > rect['x1'] and y > rect['y1'] and x < rect['x2'] and y < rect['y2']:
        self.position_utg_plus = n
        self.dealer_position = (n + 3) % 6  # 0 is myself, 1 is player to the left

    if self.position_utg_plus == '':
      raise Exception('Dealer not found')

    self.big_blind_position_abs_all = (self.dealer_position + 2) % 6  # 0 is myself, 1 is player to my left
    self.big_blind_position_abs_op = self.big_blind_position_abs_all - 1
    return self.dealer_position

  def GetMyCards(self):
    coord = self.coords['MyCards']
    table_image = self.screen[
        (self.topLeftPos[1] + coord['y1']) : (self.topLeftPos[1] + coord['y2']),
        (self.topLeftPos[0] + coord['x1']) : (self.topLeftPos[0] + coord['x2'])]
    self.mycards = []
    for key, card_image in self.card_images.items():
      res = cv2.matchTemplate(table_image, card_image, cv2.TM_SQDIFF_NORMED)
      min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
      if min_val < 0.01:
        self.mycards.append(key)
    return self.mycards

  def checkFastFold(self, preflop_sheet, mouse):
    m = MonteCarlo()
    crd1, crd2 = m.get_two_short_notation(self.mycards)
    crd1 = crd1.upper()
    crd2 = crd2.upper()
    sheet_name = str(self.position_utg_plus + 1)
    if sheet_name == '6': return True

    sheet = preflop_sheet[sheet_name]
    sheet['Hand'] = sheet['Hand'].apply(lambda x: str(x).upper())
    handlist = set(sheet['Hand'].tolist())

    found_card = ''

    if crd1 in handlist:
      found_card = crd1
    elif crd2 in handlist:
      found_card = crd2
    elif crd1[0:2] in handlist:
      found_card = crd1[0:2]

    if found_card == '':
      self.bot.Fold()
      return False
    return True

  def InitGetOtherPlayersInfo(self):
    other_player = {}
    other_player['utg_position'] = ''
    other_player['name'] = ''
    other_player['status'] = ''
    other_player['funds'] = ''
    other_player['pot'] = ''
    other_player['decision'] = ''
    self.other_players = []
    for i in range(5):
      op = other_player.copy()
      op['abs_position'] = i
      self.other_players.append(op)

  def Crop(self, coord):
    return self.screen[
        (self.topLeftPos[1] + coord['y1']) : (self.topLeftPos[1] + coord['y2']),
        (self.topLeftPos[0] + coord['x1']) : (self.topLeftPos[0] + coord['x2'])]

  def GetOtherPlayerNames(self):
    for i in range(5):
      coord = self.coords['PlayerName'][i]

      player_image_raw = Image.fromarray(self.Crop(coord))
      basewidth = 500
      wpercent = basewidth / float(player_image_raw.size[0])
      hsize = int((float(player_image_raw.size[1]) * float(wpercent)))

      player_image = player_image_raw.resize((basewidth, hsize), Image.ANTIALIAS)
      player_image.save('pics/player_name%s.png' % i)

      try:
        recognizedText = pytesseract.image_to_string(player_image)
        recognizedText = re.sub(r'[\W+]', '', recognizedText)
        self.other_players[i]['name'] = recognizedText
      except Exception as e:
        self.logger.debug("Pyteseract error in player name recognition: " + str(e))
    return [player['name'] for player in self.other_players]

  def GetOtherPlayerFunds(self):
    for i in range(5):
      coord = self.coords['PlayerFund'][i]
      player_fund = Image.fromarray(self.Crop(coord))
      value = common.GetOcrFloat(player_fund, 'player_fund%s' % i)
      value = float(value) if value != '' else ''
      self.other_players[i]['funds'] = value
    return [player['funds'] for player in self.other_players]

  def GetOtherPlayerPots(self):
    for i in range(5):
      coord = self.coords['PlayerPot'][i]
      player_pot = Image.fromarray(self.Crop(coord))
      value = common.GetOcrFloat(player_pot, 'player_pot%s' % i)
      value = float(value) if value != '' else ''
      self.other_players[i]['pot'] = value
    return [player['pot'] for player in self.other_players]

  def GetBotPot(self):
    coord = self.coords['PlayerPot'][5]
    player_pot = Image.fromarray(self.Crop(coord))
    value = common.GetOcrFloat(player_pot, 'player_pot%s' % i)
    value = float(value) if value != '' else ''
    self.bot_pot = value
    return value

  def Debug(self, message):
    print(message)

  def get_raisers_and_callers(self, reference_pot, small_blind, big_blind):
    first_raiser = np.nan
    second_raiser = np.nan
    first_caller = np.nan

    for n in range(5):  # n is absolute position of other player, 0 is player after bot
      # less myself as 0 is now first other player to my left and no longer myself
      i = (self.dealer_position + n + 3 - 2) % 5
      self.Debug("Go through pots to find raiser abs: {0} {1}".format(i, self.other_players[i]['pot']))
      if self.other_players[i]['pot'] != '':  # check if not empty (otherwise can't convert string)
          if self.other_players[i]['pot'] > reference_pot:
              # reference pot is bb for first round and bot for second round
              if np.isnan(first_raiser):
                  first_raiser = int(i)
                  first_raiser_pot = self.other_players[i]['pot']
              else:
                  if self.other_players[i]['pot'] > first_raiser_pot:
                      second_raiser = int(i)

    first_raiser_utg = get_utg_from_abs_pos(first_raiser, self.dealer_position)
    highest_raiser = np.nanmax([first_raiser, second_raiser])
    second_raiser_utg = get_utg_from_abs_pos(second_raiser, self.dealer_position)

    first_possible_caller = int(self.big_blind_position_abs_op + 1) if np.isnan(highest_raiser) else int(
        highest_raiser + 1)
    self.Debug("First possible potential caller is: " + str(first_possible_caller))

    # get first caller after raise in preflop
    for n in range(first_possible_caller, 5):  # n is absolute position of other player, 0 is player after bot
        self.Debug(
            "Go through pots to find caller abs: " + str(n) + ": " + str(self.other_players[n]['pot']))
        if self.other_players[n]['pot'] != '':  # check if not empty (otherwise can't convert string)
            if (self.other_players[n]['pot'] == big_blind and not n == self.big_blind_position_abs_op) or \
                            self.other_players[n]['pot'] > big_blind:
                first_caller = int(n)
                break

    first_caller_utg = get_utg_from_abs_pos(first_caller, self.dealer_position)

    # check for callers between bot and first raiser. If so, first raiser becomes second raiser and caller becomes first raiser
    first_possible_caller = 0
    if self.position_utg_plus == 3: first_possible_caller = 1
    if self.position_utg_plus == 4: first_possible_caller = 2
    if not np.isnan(first_raiser):
        for n in range(first_possible_caller, first_raiser):
            if self.other_players[n]['status'] == 1 and \
                    not (self.other_players[n]['utg_position'] == 5) and \
                    not (self.other_players[n]['utg_position'] == 4) and \
                    not (self.other_players[n]['pot'] == ''):
                second_raiser = first_raiser
                first_raiser = n
                first_raiser_utg = get_utg_from_abs_pos(first_raiser, self.dealer_position)
                second_raiser_utg = get_utg_from_abs_pos(second_raiser, self.dealer_position)
                break

    self.Debug("First raiser abs: " + str(first_raiser))
    self.Debug("Second raiser abs: " + str(second_raiser))
    self.Debug("First caller abs: " + str(first_caller))

    return first_raiser, second_raiser, first_caller, first_raiser_utg, second_raiser_utg, first_caller_utg


class Bot:
  def Fold(self):
    print('me: folds')


@logged
@traced
class Table(object):
    # General tools that are used to operate the pokerbot and are valid for all tables
    def __init__(self, p, gui_signals, game_logger, version):
        self.version = version
        self.ip = ''
        self.load_templates(p)
        self.load_coordinates()
        # self.__log = logging.getLogger('table')
        self.__log.setLevel(logging.DEBUG)
        self.gui_signals = gui_signals
        self.game_logger = game_logger


# mouse = MouseMoverTableBased(tableType)

tableType = 'PS'
self = NewTable(Bot())
self.LoadCards(tableType)
self.fakeScreenFilename = 'config_gen/table.png'
self.TakeFakeScreenshot()
self.GetTopLeftCorner()
self.GetTableCards()
self.GetDealerPosition()
self.GetMyCards()
preflop_sheet = pandas.read_excel('decisionmaker/preflop.xlsx', sheetname=None)
self.InitGetOtherPlayersInfo()
self.GetOtherPlayerNames()
self.GetOtherPlayerFunds()
self.GetOtherPlayerPots()

i = 0

  def GetOtherPlayerStatus(self, history, small_blind, big_blind):
    self.covered_players = 0
    for i in range(5):
      coord = self.coords['PlayerStatus'][i]
      try:
        common.FindTemplate(self.coveredCardPattern, self.Crop(coord), 0.01)
        self.covered_players += 1
        self.other_players[i]['status'] = 1
      except:
        self.other_players[i]['status'] = 0

      self.other_players[i]['utg_position'] = get_utg_from_abs_pos(
          self.other_players[i]['abs_position'], self.dealer_position)
    self.other_active_players = sum([v['status'] for v in
      self.other_players[0:5]])

    if self.gameStage == "PreFlop":
      self.playersBehind = sum(
          [v['status'] for v in self.other_players if v['abs_position'] >= self.dealer_position + 3 - 1])
    else:
      self.playersBehind = sum(
          [v['status'] for v in self.other_players if v['abs_position'] >= self.dealer_position + 1 - 1])
    self.playersAhead = self.other_active_players - self.playersBehind
    self.isHeadsUp = True if self.other_active_players < 2 else False

    if history.round_number == 0:
      reference_pot = big_blind
    else:
      reference_pot = self.GetBotPot(p)

    # get first raiser in (tested for preflop)
    self.first_raiser, \
    self.second_raiser, \
    self.first_caller, \
    self.first_raiser_utg, \
    self.second_raiser_utg, \
    self.first_caller_utg = \
        self.get_raisers_and_callers(reference_pot, small_blind, big_blind)

    def load_templates_deprecated(self, p):
        self.cardImages = dict()
        self.img = dict()
        self.tbl = p.selected_strategy['pokerSite']
        values = "23456789TJQKA"
        suites = "CDHS"
        if self.tbl == 'SN': suites = suites.lower()

        for x in values:
            for y in suites:
                name = "pics/" + self.tbl[0:2] + "/" + x + y + ".png"
                if os.path.exists(name):
                    self.img[x + y.upper()] = Image.open(name)
                    # if self.tbl=='SN':
                    #     self.img[x + y.upper()]=self.crop_image(self.img[x + y.upper()], 5,5,20,45)

                    self.cardImages[x + y.upper()] = cv2.cvtColor(np.array(self.img[x + y.upper()]), cv2.COLOR_BGR2RGB)

                    # (thresh, self.cardImages[x + y]) =
                    # cv2.threshold(self.cardImages[x + y], 128, 255,
                    # cv2.THRESH_BINARY | cv2.THRESH_OTSU)
                else:
                    self.__log.critical("Card template File not found: " + str(x) + str(y) + ".png")

        name = "pics/" + self.tbl[0:2] + "/button.png"
        template = Image.open(name)
        self.button = cv2.cvtColor(np.array(template), cv2.COLOR_BGR2RGB)

        name = "pics/" + self.tbl[0:2] + "/topleft.png"
        template = Image.open(name)
        self.topLeftCorner = cv2.cvtColor(np.array(template), cv2.COLOR_BGR2RGB)

        if self.tbl[0:2] == 'SN':
            name = "pics/" + self.tbl[0:2] + "/topleft2.png"
            template = Image.open(name)
            self.topLeftCorner2 = cv2.cvtColor(np.array(template), cv2.COLOR_BGR2RGB)

            name = "pics/" + self.tbl[0:2] + "/topleft3.png"
            template = Image.open(name)
            self.topLeftCorner_snowieadvice1 = cv2.cvtColor(np.array(template), cv2.COLOR_BGR2RGB)

            name = "pics/" + self.tbl[0:2] + "/topleftLA.png"
            template = Image.open(name)
            self.topLeftCorner_snowieadvice2 = cv2.cvtColor(np.array(template), cv2.COLOR_BGR2RGB)

        name = "pics/" + self.tbl[0:2] + "/coveredcard.png"
        template = Image.open(name)
        self.coveredCardHolder = cv2.cvtColor(np.array(template), cv2.COLOR_BGR2RGB)

        name = "pics/" + self.tbl[0:2] + "/imback.png"
        template = Image.open(name)
        self.ImBack = cv2.cvtColor(np.array(template), cv2.COLOR_BGR2RGB)

        name = "pics/" + self.tbl[0:2] + "/check.png"
        template = Image.open(name)
        self.check = cv2.cvtColor(np.array(template), cv2.COLOR_BGR2RGB)

        name = "pics/" + self.tbl[0:2] + "/call.png"
        template = Image.open(name)
        self.call = cv2.cvtColor(np.array(template), cv2.COLOR_BGR2RGB)

        name = "pics/" + self.tbl[0:2] + "/smalldollarsign1.png"
        template = Image.open(name)
        self.smallDollarSign1 = cv2.cvtColor(np.array(template), cv2.COLOR_BGR2RGB)

        name = "pics/" + self.tbl[0:2] + "/allincallbutton.png"
        template = Image.open(name)
        self.allInCallButton = cv2.cvtColor(np.array(template), cv2.COLOR_BGR2RGB)

        name = "pics/" + self.tbl[0:2] + "/lostEverything.png"
        template = Image.open(name)
        self.lostEverything = cv2.cvtColor(np.array(template), cv2.COLOR_BGR2RGB)

        name = "pics/" + self.tbl[0:2] + "/dealer.png"
        template = Image.open(name)
        self.dealer = cv2.cvtColor(np.array(template), cv2.COLOR_BGR2RGB)

        name = "pics/" + self.tbl[0:2] + "/betbutton.png"
        template = Image.open(name)
        self.betbutton = cv2.cvtColor(np.array(template), cv2.COLOR_BGR2RGB)

    def load_coordinates(self):
        with open('coordinates.txt', 'r') as inf:
            c = eval(inf.read())
            self.coo = c['screen_scraping']

    def TakeScreenshot():
      try:
        vb = VirtualBoxController()
        self.screen = cv2.cvtColor(np.array(vb.get_screenshot_vbox()), cv2.COLOR_BGR2RGB)
        self.logger.debug("Screenshot taken from virtual machine")
      except:
        self.logger.warning("No virtual machine found. Press SETUP to re initialize the VM controller")

    def take_screenshot(self, initial, p):
        if initial:
            self.gui_signals.signal_status.emit("")
            self.gui_signals.signal_progressbar_reset.emit()
            if self.gui_signals.exit_thread == True: sys.exit()
            if self.gui_signals.pause_thread == True:
                while self.gui_signals.pause_thread == True:
                    time.sleep(1)
                    if self.gui_signals.exit_thread == True: sys.exit()

        time.sleep(0.1)
        config = ConfigObj("config.ini")
        control = config['control']
        if control == 'Direct mouse control':
            self.entireScreenPIL = ImageGrab.grab()

        else:
            try:
                vb = VirtualBoxController()
                self.entireScreenPIL = vb.get_screenshot_vbox()
                self.__log.debug("Screenshot taken from virtual machine")
            except Exception as e:
                self.__log.warning("No virtual machine found. Press SETUP to re"
                        "initialize the VM controller" + e)
                # gui_signals.signal_open_setup.emit(p,L)
                self.entireScreenPIL = ImageGrab.grab()

        self.gui_signals.signal_status.emit(str(p.current_strategy))
        self.gui_signals.signal_progressbar_increase.emit(5)
        return True

    def find_template_on_screen(self, template, screenshot, threshold):
        # 'cv2.TM_CCOEFF', 'cv2.TM_CCOEFF_NORMED', 'cv2.TM_CCORR',
        # 'cv2.TM_CCORR_NORMED', 'cv2.TM_SQDIFF', 'cv2.TM_SQDIFF_NORMED']
        method = eval('cv2.TM_SQDIFF_NORMED')
        # Apply template Matching
        res = cv2.matchTemplate(screenshot, template, method)
        loc = np.where(res <= threshold)

        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)

        # If the method is TM_SQDIFF or TM_SQDIFF_NORMED, take minimum
        if method in [cv2.TM_SQDIFF, cv2.TM_SQDIFF_NORMED]:
            bestFit = min_loc
        else:
            bestFit = max_loc

        count = 0
        points = []
        for pt in zip(*loc[::-1]):
            # cv2.rectangle(img, pt, (pt[0] + w, pt[1] + h), (0,0,255), 2)
            count += 1
            points.append(pt)
        # plt.subplot(121),plt.imshow(res)
        # plt.subplot(122),plt.imshow(img,cmap = 'jet')
        # plt.imshow(img, cmap = 'gray', interpolation = 'bicubic')
        # plt.show()
        return count, points, bestFit, min_val

    def get_ocr_float(self, img_orig, name, force_method=0, binarize=False):
        def binarize_array(image, threshold=200):
            """Binarize a numpy array."""
            numpy_array = np.array(image)
            for i in range(len(numpy_array)):
                for j in range(len(numpy_array[0])):
                    if numpy_array[i][j] > threshold:
                        numpy_array[i][j] = 255
                    else:
                        numpy_array[i][j] = 0
            return Image.fromarray(numpy_array)

        def fix_number(t, force_method):
            t = t.replace("I", "1").replace("Â°lo", "").replace("O", "0").replace("o", "0") \
                .replace("-", ".").replace("D", "0").replace("I", "1").replace("_", ".").replace("-", ".") \
                .replace("B", "8").replace("..", ".").replace(",", "")
            t = re.sub("[^0123456789\.]", "", t)
            try:
                if t[0] == ".": t = t[1:]
            except:
                pass
            try:
                if t[-1] == ".": t = t[0:-1]
            except:
                pass
            try:
                if t[-1] == ".": t = t[0:-1]
            except:
                pass
            try:
                if t[-1] == "-": t = t[0:-1]
            except:
                pass
            if force_method == 1:
                try:
                    t = re.findall(r'\d{1,7}\.\d{1,2}', str(t))[0]
                except:
                    t = ''
                if t == '':
                    try:
                        t = re.findall(r'\d{1,7}', str(t))[0]
                    except:
                        t = ''

            return t

        try:
            img_orig.save('pics/ocr_debug_' + name + '.png')
        except:
            self.__log.warning("Coulnd't safe debugging png file for ocr")

        basewidth = 300
        wpercent = (basewidth / float(img_orig.size[0]))
        hsize = int((float(img_orig.size[1]) * float(wpercent)))
        img_resized = img_orig.convert('L').resize((basewidth, hsize), Image.ANTIALIAS)
        if binarize:
            img_resized = binarize_array(img_resized, 200)

        img_min = img_resized.filter(ImageFilter.MinFilter)
        # img_med = img_resized.filter(ImageFilter.MedianFilter)
        img_mod = img_resized.filter(ImageFilter.ModeFilter).filter(ImageFilter.SHARPEN)

        img_min.save('pics/ocr_debug_' + name + '_min.png')
        img_mod.save('pics/ocr_debug_' + name + '_mod.png')

        lst = []
        # try:
        #    lst.append(pytesseract.image_to_string(img_orig, none, false,"-psm 6"))
        # except exception as e:
        #    self.__log.error(str(e))

        if force_method == 0:
            try:
                # lst.append(pytesseract.image_to_string(img_min, None, False, "-psm 6"))
                lst.append(pytesseract.image_to_string(img_min))
                self.__log.debug('Number for ' + name + ' was: '+ lst[0])
            except Exception as e:
                self.__log.warning(str(e))
                try:
                    self.entireScreenPIL.save('pics/err_debug_fullscreen.png')
                except:
                    self.__log.warning("Coulnd't safe debugging png file for ocr")

        try:
            if force_method == 1 or fix_number(lst[0], force_method=0) == '':
                # lst.append(pytesseract.image_to_string(img_mod, None, False, "-psm 6"))
                # lst.append(pytesseract.image_to_string(img_min, None, False, "-psm 6"))
                lst.append(pytesseract.image_to_string(img_mod))
                lst.append(pytesseract.image_to_string(img_min))

        except UnicodeDecodeError:
            pass
        except Exception as e:
            self.__log.warning(str(e))
            try:
                self.entireScreenPIL.save('pics/err_debug_fullscreen.png')
            except:
                self.__log.warning("Coulnd't safe debugging png file for ocr")

        try:
            final_value = ''
            for i, j in enumerate(lst):
                self.__log.debug("OCR of " + name + " method " + str(i) + ": " + str(j))
                lst[i] = fix_number(lst[i], force_method) if lst[i] != '' else lst[i]
                final_value = lst[i] if final_value == '' else final_value

            self.__log.info(name + " FINAL VALUE: " + str(final_value))
            if final_value == '':
                return ''
            else:
                return float(final_value)

        except Exception as e:
            self.__log.warning("Pytesseract Error in recognising " + name)
            self.__log.warning(str(e))
            try:
                self.entireScreenPIL.save('pics/err_debug_fullscreen.png')
            except:
                pass
            return ''

    def call_genetic_algorithm(self, p):
        self.gui_signals.signal_progressbar_increase.emit(5)
        self.gui_signals.signal_status.emit("Updating charts and work in background")
        n = self.game_logger.get_game_count(p.current_strategy)
        lg = int(p.selected_strategy['considerLastGames'])  # only consider lg last games to see if there was a loss
        f = self.game_logger.get_strategy_return(p.current_strategy, lg)
        self.gui_signals.signal_label_number_update.emit('gamenumber', str(int(n)))

        total_winnings = self.game_logger.get_strategy_return(p.current_strategy, 9999999)

        winnings_per_bb_100 = total_winnings / p.selected_strategy['bigBlind'] / n * 100 if n > 0 else 0

        self.__log.info("Total Strategy winnings: %s", total_winnings)
        self.__log.info("Winnings in BB per 100 hands: %s", np.round(winnings_per_bb_100,2))
        self.gui_signals.signal_label_number_update.emit('winnings', str(np.round(winnings_per_bb_100, 2)))

        self.__log.info("Game #" + str(n) + " - Last " + str(lg) + ": $" + str(f))

        if n % int(p.selected_strategy['strategyIterationGames']) == 0 and f < float(
                p.selected_strategy['minimumLossForIteration']):
            self.gui_signals.signal_status.emit("***Improving current strategy***")
            self.__log.info("***Improving current strategy***")
            # winsound.Beep(500, 100)
            GeneticAlgorithm(True, self.game_logger)
            p.read_strategy()
        else:
            pass
            # self.__log.debug("Criteria not met for running genetic algorithm. Recommendation would be as follows:")
            # if n % 50 == 0: GeneticAlgorithm(False, logger, L)

    def crop_image(self, original, left, top, right, bottom):
        # original.show()
        width, height = original.size  # Get dimensions
        cropped_example = original.crop((left, top, right, bottom))
        # cropped_example.show()
        return cropped_example


    def derive_preflop_sheet_name(self, t, h, first_raiser_utg, first_caller_utg, second_raiser_utg):
        first_raiser_string = 'R' if not np.isnan(first_raiser_utg) else ''
        first_raiser_number = str(first_raiser_utg + 1) if first_raiser_string != '' else ''

        second_raiser_string = 'R' if not np.isnan(second_raiser_utg) else ''
        second_raiser_number = str(second_raiser_utg + 1) if second_raiser_string != '' else ''

        first_caller_string = 'C' if not np.isnan(first_caller_utg) else ''
        first_caller_number = str(first_caller_utg + 1) if first_caller_string != '' else ''

        round_string = '2' if h.round_number == 1 else ''

        sheet_name = str(t.position_utg_plus + 1) + \
                     round_string + \
                     str(first_raiser_string) + str(first_raiser_number) + \
                     str(second_raiser_string) + str(second_raiser_number) + \
                     str(first_caller_string) + str(first_caller_number)

        if h.round_number == 2:
            sheet_name = 'R1R2R1A2'

        self.preflop_sheet_name = sheet_name
        return self.preflop_sheet_name
