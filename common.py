import cv2
import re
import sys
from PIL import Image
import pytesseract
from PIL import ImageFilter
import numpy as np

def GetCvImage(filename):
  return cv2.cvtColor(np.array(Image.open(filename)), cv2.COLOR_BGR2RGB)

class Empty:
  pass

def FindTemplateOnScreen(template, screenshot, threshold):
  method = cv2.TM_SQDIFF_NORMED
  # Apply template Matching
  res = cv2.matchTemplate(screenshot, template, method)
  loc = np.where(res <= threshold)
  min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
  bestFit = min_loc
  points = []
  # reverse x and y.
  for pt in zip(*loc[::-1]):
    points.append((int(pt[0]), int(pt[1])))
  return len(points), points, bestFit, min_val


def FindTemplate(template, screenshot, threshold=0.1):
  num_point, points, _, _, = FindTemplateOnScreen(template, screenshot, threshold)
  if num_point != 1:
    RaiseTemplateNotFound('', template, screenshot)
  return points[0]

def RaiseTemplateNotFound(name, template, screenshot):
  cv2.imwrite('logs/not_found.png', template)
  cv2.imwrite('logs/in_screen.png', screenshot)
  raise Exception('Template %s not found' % name)

def GetOcrFloat(img_orig, name, force_method=0, binarize=False):
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
            .replace("B", "8").replace("..", ".")
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
                t = re.findall(r'\d{1,3}\.\d{1,2}', str(t))[0]
            except:
                t = ''
            if t == '':
                try:
                    t = re.findall(r'\d{1,3}', str(t))[0]
                except:
                    t = ''
        try:
          if float(t) == 0:
              return ''
        except:
            return ''

        return t

    try:
        img_orig.save('pics/ocr_debug_' + name + '.png')
    except:
        self.logger.warning("Coulnd't safe debugging png file for ocr")

    basewidth = 300
    wpercent = (basewidth / float(img_orig.size[0]))
    hsize = int((float(img_orig.size[1]) * float(wpercent)))
    img_resized = img_orig.convert('L').resize((basewidth, hsize), Image.ANTIALIAS)
    if binarize:
        img_resized = binarize_array(img_resized, 200)

    img_min = img_resized.filter(ImageFilter.MinFilter)
    img_mod = img_resized.filter(ImageFilter.ModeFilter).filter(ImageFilter.SHARPEN)
    # img_min.save('pics/ocr_debug_%s_resized.png' % name)

    lst = []

    if force_method == 0:
        try:
            lst.append(pytesseract.image_to_string(img_min))
        except:
            print("Unexpected error:", sys.exc_info()[0])
            raise

    try:
        if force_method == 1 or fix_number(lst[0], force_method=0) == '':
            lst.append(pytesseract.image_to_string(img_mod))
            lst.append(pytesseract.image_to_string(img_min))
    except UnicodeDecodeError:
        pass
    except Exception as e:
        print("Unexpected error:", sys.exc_info()[0])
        raise

    final_value = ''
    for i, j in enumerate(lst):
        # self.logger.debug("OCR of " + name + " method " + str(i) + ": " + str(j))
        lst[i] = fix_number(lst[i], force_method) if lst[i] != '' else lst[i]
        final_value = lst[i] if final_value == '' else final_value

    # self.logger.info(name + " FINAL VALUE: " + str(final_value))
    if final_value == '':
        return ''
    else:
        return float(final_value)

# img_orig = Image.open('pics/ocr_debug_player_pot2.png')
# pytesseract.image_to_string(img_min, config='--psm 7 digits')
