# style_library.py

# Default (varsayılan) stil tanımı
def_style_blist = """
QPushButton {
    background-color: rgb(238, 222, 8);
    border-radius: 4px;
    padding: 3px;
    color: black;
}
QPushButton:hover {
    background-color: rgb(252, 145, 22);
    color: black;
}
"""

# Seçili (tıklanan) buton stili
selct_style_blist = """
QPushButton {
    background-color: rgb(48, 74, 74);
    border-radius: 4px;
    padding: 3px;
    color: white;
}
QPushButton:hover {
    background-color: rgb(91, 141, 141);
    color: white;
}
"""
track_buttons_def_style = """
QPushButton {
    background-color: rgb(255, 71, 71);
    border-radius: 4px;
    padding: 3px;
    color: black;
}
QPushButton:hover {
    background-color: rgb(252, 0, 0);
    color: black;
}
"""

# Seçili (tıklanan) buton stili
track_buttons_selct_style = """
QPushButton {
    background-color: rgb(0, 215, 43);
    border-radius: 4px;
    padding: 3px;
    color: white;
}
QPushButton:hover {
    background-color: rgb(37, 186, 57);
    color: white;
}
"""


map_button_style = """
QPushButton {
    background-color: rgb(30, 30, 255);
    border-radius: 4px;
    padding: 3px;
    color: white;
    font-size: 12px;      /* yazı boyutu */
}
QPushButton:hover {
    background-color: rgb(0, 0, 200);
    color: white;
}
"""


blist_buttons_style = """
QPushButton {
    background-color: rgb(238, 222, 8);
    border-radius: 4px;
    padding: 3px;
    color: black;
}
QPushButton:hover {
    background-color: rgb(252, 145, 22);
    color: rgb(0, 0, 0);
}
"""
track_buttons_style = """
QPushButton {
    background-color: rgb(255, 0, 68);
    border-radius: 4px;
    padding: 3px;
    color: black;
}
QPushButton:hover {
    background-color: rgb(252, 145, 22);
    color: rgb(0, 0, 0);
}
"""
mode_buttons_def_style = """
QPushButton {
    background-color: rgb(248, 87, 87);
    border-radius: 10px;
    padding: 10px;
    color: black;
}
QPushButton:hover {
    background-color: rgb(220, 29, 0);
    color: black;
}
"""

mode_buttons_selct_style = """
QPushButton {
    background-color: green;
    border-radius: 10px;
    padding: 10px;
    color: white;
}
QPushButton:hover {
    background-color: rgb(0, 168, 11);
    color: white;
}
"""


terminal_output_style = """
QTextEdit {
    color: #00FF00;
    background-color: #000000;
    border: 2px solid #FFFFFF;
    border-radius: 4px;
    padding: 4px;
}
"""
terminal_input_style = """
QLineEdit {
    color: #00FF00;
    background-color: #000000;
    border: 2px solid #FFFFFF;
    border-radius: 4px;
    padding: 4px;
}
"""


