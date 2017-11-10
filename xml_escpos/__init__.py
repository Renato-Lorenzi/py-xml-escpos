# -*- coding: utf-8 -*-
# Based on https://github.com/fvdsn/py-xml-escpos
#
#

import math
import re
import xml.etree.ElementTree as ET
from escpos.constants import *


TXT_DOUBLE = '\x1b\x21\x30'  # Double height & Width
BARCODE_DOUBLE_WIDTH = 2
BARCODE_HRI_TOP = 1

try:
    import jcconv
except ImportError:
    jcconv = None

try:
    import qrcode
except ImportError:
    qrcode = None


def utfstr(stuff):
    """ converts stuff to string and does without failing if stuff is a utf8 string """
    if isinstance(stuff, basestring):
        return stuff
    else:
        return str(stuff)


class StyleStack:
    """ 
    The stylestack is used by the xml receipt serializer to compute the active styles along the xml
    document. Styles are just xml attributes, there is no css mechanism. But the style applied by
    the attributes are inherited by deeper nodes.
    """

    def __init__(self):
        self.stack = []
        self.defaults = {  # default style values
            'align': 'left',
            'underline': 'off',
            'bold': 'off',
            'size': 'normal',
            'font': 'a',
            'width': 48,
            'indent': 0,
            'tabwidth': 2,
            'bullet': ' - ',
            'line-ratio': 0.5,
            'color': 'black',

            'value-decimals': 2,
            'value-symbol': '',
            'value-symbol-position': 'after',
            'value-autoint': 'off',
            'value-decimals-separator': '.',
            'value-thousands-separator': ',',
            'value-width': 0,

        }

        self.types = {  # attribute types, default is string and can be ommitted
            'width': 'int',
            'indent': 'int',
            'tabwidth': 'int',
            'line-ratio': 'float',
            'value-decimals': 'int',
            'value-width': 'int',
        }
        self.escpos_keys = ['align', 'underline', 'bold', 'font', 'size', 'color']

        self.push(self.defaults)

    def get(self, style):
        """ what's the value of a style at the current stack level"""
        level = len(self.stack) - 1
        while level >= 0:
            if style in self.stack[level]:
                return self.stack[level][style]
            else:
                level = level - 1
        return None

    def enforce_type(self, attr, val):
        """converts a value to the attribute's type"""
        if not attr in self.types:
            return utfstr(val)
        elif self.types[attr] == 'int':
            return int(float(val))
        elif self.types[attr] == 'float':
            return float(val)
        else:
            return utfstr(val)

    def push(self, style={}):
        """push a new level on the stack with a style dictionnary containing style:value pairs"""
        _style = {}
        for attr in style:
            _style[attr] = self.enforce_type(attr, style[attr])
        self.stack.append(_style)

    def set(self, style={}):
        """overrides style values at the current stack level"""
        _style = {}
        for attr in style:
            self.stack[-1][attr] = self.enforce_type(attr, style[attr])

    def pop(self):
        """ pop a style stack level """
        if len(self.stack) > 1:
            self.stack = self.stack[:-1]

    def get_styles(self):
        """ Get actual styles in stack """
        ret = {}
        for style in self.escpos_keys:
            ret[style] = self.get(style)
        return ret


class XmlSerializer:
    """ 
    Converts the xml inline / block tree structure to a string,
    keeping track of newlines and spacings.
    The string is outputted asap to the provided escpos driver.
    """

    def __init__(self, printer):
        self.printer = printer
        self.stack = ['block']

    def start_inline(self, stylestack=None):
        """ starts an inline entity with an optional style definition """
        self.stack.append('inline')
        if stylestack:
            self.style(stylestack)

    def start_block(self, stylestack=None):
        """ starts a block entity with an optional style definition """
        self.stack.append('block')
        if stylestack:
            self.style(stylestack)

    def end_entity(self):
        """ ends the entity definition. (but does not cancel the active style!) """
        if self.stack[-1] == 'block':
            self.printer.text('\n')

        if len(self.stack) > 1:
            self.stack = self.stack[:-1]

    def pre(self, text):
        """ puts a string of text in the entity keeping the whitespace intact """
        if text:
            self.printer.text(text)

    def text(self, text):
        """ puts text in the entity. Whitespace and newlines are stripped to single spaces. """
        if text:
            text = utfstr(text)
            text = text.strip()
            text = re.sub('\s+', ' ', text)
            if text:
                self.printer.text(text)

    def linebreak(self):
        """ inserts a linebreak in the entity """
        self.printer.text('\n')

    def style(self, stylestack):
        """ apply a style to the entity (only applies to content added after the definition) """
        self.printer.apply_style(stylestack)


class XmlLineSerializer:
    """
    This is used to convert a xml tree into a single line, with a left and a right part.
    The content is not output to escpos directly, and is intended to be fedback to the
    XmlSerializer as the content of a block entity.
    """

    def __init__(self, indent=0, tabwidth=2, width=48, ratio=0.5):
        self.tabwidth = tabwidth
        self.indent = indent
        self.width = max(0, width - int(tabwidth * indent))
        self.lwidth = int(self.width * ratio)
        self.rwidth = max(0, self.width - self.lwidth)
        self.clwidth = 0
        self.crwidth = 0
        self.lbuffer = ''
        self.rbuffer = ''
        self.left = True

    def _txt(self, txt):
        if self.left:
            if self.clwidth < self.lwidth:
                txt = txt[:max(0, self.lwidth - self.clwidth)]
                self.lbuffer += txt
                self.clwidth += len(txt)
        else:
            if self.crwidth < self.rwidth:
                txt = txt[:max(0, self.rwidth - self.crwidth)]
                self.rbuffer += txt
                self.crwidth += len(txt)

    def start_inline(self, stylestack=None):
        if (self.left and self.clwidth) or (not self.left and self.crwidth):
            self._txt(' ')

    def start_block(self, stylestack=None):
        self.start_inline(stylestack)

    def end_entity(self):
        pass

    def pre(self, text):
        if text:
            self._txt(text)

    def text(self, text):
        if text:
            text = utfstr(text)
            text = text.strip()
            text = re.sub('\s+', ' ', text)
            if text:
                self._txt(text)

    def linebreak(self):
        pass

    def style(self, stylestack):
        pass

    def start_right(self):
        self.left = False

    def get_line(self):
        return ' ' * self.indent * self.tabwidth + self.lbuffer + ' ' * (
            self.width - self.clwidth - self.crwidth) + self.rbuffer


def receipt(printer, xml):
    """
    Prints an xml based receipt definition
    """

    def strclean(string):
        if not string:
            string = ''
        string = string.strip()
        string = re.sub('\s+', ' ', string)
        return string

    def format_value(value, decimals=3, width=0, decimals_separator='.', thousands_separator=',', autoint=False,
                     symbol='', position='after'):
        decimals = max(0, int(decimals))
        width = max(0, int(width))
        value = float(value)

        if autoint and math.floor(value) == value:
            decimals = 0
        if width == 0:
            width = ''

        if thousands_separator:
            formatstr = "{:" + str(width) + ",." + str(decimals) + "f}"
        else:
            formatstr = "{:" + str(width) + "." + str(decimals) + "f}"

        ret = formatstr.format(value)
        ret = ret.replace(',', 'COMMA')
        ret = ret.replace('.', 'DOT')
        ret = ret.replace('COMMA', thousands_separator)
        ret = ret.replace('DOT', decimals_separator)

        if symbol:
            if position == 'after':
                ret = ret + symbol
            else:
                ret = symbol + ret
        return ret

    def print_barcode(stylestack, serializer, elem):
        serializer.start_block(stylestack)
        kwargs = {'align_ct': elem.attrib['align_ct'] == 'on' if 'align_ct' in elem.attrib else False}
        if 'height' in elem.attrib:
            kwargs['height'] = int(elem.attrib['height'])
        if 'width' in elem.attrib:
            kwargs['width'] = int(elem.attrib['width'])
        if 'pos' in elem.attrib:
            kwargs['pos'] = elem.attrib['pos']        

        printer.barcode(strclean(elem.text), elem.attrib['encoding'], **kwargs)
        serializer.end_entity()

    def print_elem(stylestack, serializer, elem, indent=0):

        elem_styles = {
            'h1': {'bold': 'on', 'size': 'double'},
            'h2': {'size': 'double'},
            'h3': {'bold': 'on', 'size': 'double-height'},
            'h4': {'size': 'double-height'},
            'h5': {'bold': 'on'},
            'em': {'font': 'b'},
            'b': {'bold': 'on'},
        }

        stylestack.push()
        if elem.tag in elem_styles:
            stylestack.set(elem_styles[elem.tag])
        stylestack.set(elem.attrib)

        if elem.tag in (
                'p', 'div', 'section', 'article', 'receipt', 'header', 'footer', 'li', 'h1', 'h2', 'h3', 'h4', 'h5'):
            serializer.start_block(stylestack)
            serializer.text(elem.text)
            for child in elem:
                print_elem(stylestack, serializer, child)
                serializer.start_inline(stylestack)
                serializer.text(child.tail)
                serializer.end_entity()
            serializer.end_entity()

        elif elem.tag in ('span', 'em', 'b', 'left', 'right'):
            serializer.start_inline(stylestack)
            serializer.text(elem.text)
            for child in elem:
                print_elem(stylestack, serializer, child)
                serializer.start_inline(stylestack)
                serializer.text(child.tail)
                serializer.end_entity()
            serializer.end_entity()

        elif elem.tag == 'value':
            serializer.start_inline(stylestack)
            serializer.pre(format_value(
                elem.text,
                decimals=stylestack.get('value-decimals'),
                width=stylestack.get('value-width'),
                decimals_separator=stylestack.get('value-decimals-separator'),
                thousands_separator=stylestack.get('value-thousands-separator'),
                autoint=(stylestack.get('value-autoint') == 'on'),
                symbol=stylestack.get('value-symbol'),
                position=stylestack.get('value-symbol-position')
            ))
            serializer.end_entity()

        elif elem.tag == 'line':
            width = stylestack.get('width')
            if stylestack.get('size') in ('double', 'double-width'):
                width = width / 2

            lineserializer = XmlLineSerializer(stylestack.get('indent') + indent, stylestack.get('tabwidth'), width,
                                               stylestack.get('line-ratio'))
            serializer.start_block(stylestack)
            for child in elem:
                if child.tag == 'left':
                    print_elem(stylestack, lineserializer, child, indent=indent)
                elif child.tag == 'right':
                    lineserializer.start_right()
                    print_elem(stylestack, lineserializer, child, indent=indent)
            serializer.pre(lineserializer.get_line())
            serializer.end_entity()

        elif elem.tag == 'pre':
            serializer.start_block(stylestack)
            serializer.pre(elem.text)
            serializer.end_entity()

        elif elem.tag == 'hr':
            width = stylestack.get('width')
            if stylestack.get('size') in ('double', 'double-width'):
                width = width / 2
            serializer.start_block(stylestack)
            serializer.text('-' * width)
            serializer.end_entity()

        elif elem.tag == 'br':
            serializer.linebreak()

        elif elem.tag == 'img':
            if 'src' in elem.attrib and 'data:' in elem.attrib['src']:
                printer.print_base64_image(elem.attrib['src'])

        elif elem.tag == 'barcode' and 'encoding' in elem.attrib:
            print_barcode(stylestack, serializer, elem)

        elif elem.tag == 'cut':
            printer.cut()
        elif elem.tag == 'partialcut':
            printer.cut(mode='part')
        elif elem.tag == 'cashdraw':
            printer.cashdraw(2)
            printer.cashdraw(5)

        stylestack.pop()

    stylestack = StyleStack()
    serializer = XmlSerializer(printer)
    root = ET.fromstring(xml.encode('utf-8'))
    if 'sheet' in root.attrib and root.attrib['sheet'] == 'slip':
        printer.set_sheet_slip_mode()
        printer.slip_sheet_mode = True
    else:
        printer.set_sheet_roll_mode()

    print_elem(stylestack, serializer, root)

    if not 'cut' in root.attrib or root.attrib['cut'] == 'true':
        printer.cut()


class DefaultXMLPrinter(object):
    def __init__(self, printer):
        self.printer = printer

    def set_sheet_slip_mode(self):
        pass

    def set_sheet_roll_mode(self):
        pass

    def apply_style(self, stylestack):
        pass

    def text(self, text):
        pass

    def barcode(self, code, encoding, height=64, width=3, pos="BELOW", align_ct=True):
        pass

    def cut(self):
        pass


class DarumaXMLPrinter(DefaultXMLPrinter):

    def __init__(self, printer):
        super(DarumaXMLPrinter, self).__init__(printer)
        printer.justify_center()
    def text(self, text):
        self.printer.textout(text.encode('iso-8859-1'))

    def barcode(self, code, encoding, height=64, width=3, pos="BELOW", align_ct=True):
        """ Por enquanto suporta apenas o EAN13 """
        self.printer.ean13(code + "0",
                           barcode_height=height,  # ~15mm (~9/16"),
                           barcode_width=BARCODE_DOUBLE_WIDTH,
                           barcode_hri=BARCODE_HRI_TOP)

    def cut(self):
        self.printer.text("\n\n\n\n\n")
        self.printer.device.write('\x1B\x6D')

    def apply_style(self, stylestack):
        """ Para esse tipo de impressora ainda não suporta todos os estilos"""
        styles = stylestack.get_styles()
        self.printer.set_emphasized(styles['bold'] == 'on')
        if styles['size'] == 'double':
            self.printer.set_condensed(True)
            self.printer.set_expanded(True)
        else:
            self.printer.set_condensed(False)
            self.printer.set_expanded(False)


class EscPosXMLPrinter(DefaultXMLPrinter):
    def __init__(self, printer):
        self.printer = printer
        self.printer.charcode("MULTILINGUAL")
        super(EscPosXMLPrinter, self).__init__(printer)
        self.cmds = {
            # translation from styles to escpos commands
            # some style do not correspond to escpos command are used by
            # the serializer instead
            'align': {
                'left': TXT_ALIGN_LT,
                'right': TXT_ALIGN_RT,
                'center': TXT_ALIGN_CT,
                '_order': 1,
            },
            'underline': {
                'off': TXT_UNDERL_OFF,
                'on': TXT_UNDERL_ON,
                'double': TXT_UNDERL2_ON,
                # must be issued after 'size' command
                # because ESC ! resets ESC -
                '_order': 10,
            },
            'bold': {
                'off': TXT_BOLD_OFF,
                'on': TXT_BOLD_ON,
                # must be issued after 'size' command
                # because ESC ! resets ESC -
                '_order': 10,
            },
            'font': {
                'a': TXT_FONT_A,
                'b': TXT_FONT_B,
                # must be issued after 'size' command
                # because ESC ! resets ESC -
                '_order': 10,
            },
            'size': {
                'normal': TXT_NORMAL,
                'double-height': TXT_2HEIGHT,
                'double-width': TXT_2WIDTH,
                'double': TXT_DOUBLE,
                '_order': 1,
            },
            'color': {
                'black': TXT_COLOR_BLACK,
                'red': TXT_COLOR_RED,
                '_order': 1,
            },
        }

    def set_sheet_slip_mode(self):
        self.printer._raw(SHEET_SLIP_MODE)

    def set_sheet_roll_mode(self):
        self.printer._raw(SHEET_ROLL_MODE)

    def apply_style(self, stylestack):
        self.printer._raw(self.to_escpos(stylestack))

    def to_escpos(self, stylestack):
        """ converts the current style to an escpos command string """
        cmd = ''
        ordered_cmds = self.cmds.keys()
        ordered_cmds.sort(lambda x, y: cmp(self.cmds[x]['_order'], self.cmds[y]['_order']))
        for style in ordered_cmds:
            cmd += self.cmds[style][stylestack.get(style)]
        return cmd

    def text(self, text):
        self.printer.text(text)

    def barcode(self, code, encoding, **kwargs):
        self.printer.barcode(code, encoding, **kwargs)

    def cut(self):
        self.printer.cut()