import re
from functools import reduce
from PIL import Image, ImageDraw, ImageFont
import requests
import json
from datetime import datetime, date, timedelta
import psycopg2
import sys
import os
from google_api import get_calendar_service, remove_all_events, add_event, remove_future_events
import traceback

# DB columns

print('\n\n----', datetime.now())

ID = 0
CLICKUP_ID = 1
DATE_ADDED = 2
TASK_NAME = 3
DUE_DATE = 4
DATE_DONE = 5
POINTS = 6


# for raspberry
# def connect_to_db():
#     # DATABASE
#     # Create a connection
#     conn = psycopg2.connect(
#         user="postgres",
#         password="postgres",
#         host="192.168.1.131",
#         port=5432,
#         database="digimon"
#     )

#     # Create a cursor to execute queries
#     cur = conn.cursor()
#     # END DATABASE

#     return conn, cur


# for local
def connect_to_db():
    # DATABASE
    # Create a connection
    conn = psycopg2.connect(
        user="postgres",
        password="postgres",
        host="localhost",
        port=5432,
        database="digimon"
    )

    # Create a cursor to execute queries
    cur = conn.cursor()
    # END DATABASE

    return conn, cur


cur = None
conn = None
try:
    conn, cur = connect_to_db()
    print("Connected to database")
except Exception as e:
    print(e)
    print("Cannot connect to database")


def get_saved_tasks(conn, cur):

    # Example query
    cur.execute("SELECT * FROM tasks;")
    saved_tasks = cur.fetchall()

    return [list(row) for row in saved_tasks]


def get_saved_active_tasks(conn, cur):

    # Example query
    cur.execute("""
        SELECT *
        FROM tasks
        WHERE date_added > (SELECT MAX(datetime) FROM resets)
        AND (
            date_done > (SELECT MAX(datetime) FROM resets)
            OR date_done IS NULL
        );
                """)
    saved_tasks = cur.fetchall()

    return [list(row) for row in saved_tasks]


def save_task(conn, cur, processed_task):
    """
    Inserta un task en la tabla 'tasks'.
    processed_task debe ser un dict con las keys:
    'clickup_id', 'task_name', 'due_date', 'date_done', 'points'
    """

    # Convertir timestamps en segundos a datetime (PostgreSQL TIMESTAMP)
    due_date = datetime.fromtimestamp(
        processed_task['due_date']) if processed_task['due_date'] else None
    date_done = datetime.fromtimestamp(
        processed_task['date_done']) if processed_task['date_done'] else None

    insert_query = """
        INSERT INTO tasks (clickup_id, task_name, due_date, date_done, points)
        VALUES (%s, %s, %s, %s, %s);
    """

    cur.execute(
        insert_query,
        (
            processed_task['clickup_id'],
            processed_task['task_name'],
            due_date,
            date_done,
            processed_task['points']
        )
    )


def insert_reset(conn, cur):
    """
    Inserts a new row in the 'resets' table using default values.
    """
    insert_query = "INSERT INTO resets DEFAULT VALUES;"
    cur.execute(insert_query)
    conn.commit()  # commit the transaction
    print("Inserted a new reset row.")


def get_last_reset(conn, cur):
    cur.execute("""SELECT max(datetime)
        FROM resets;""")
    last_reset = cur.fetchone()

    return last_reset[0]


def get_clickup_tasks():

    lists = {
        'tony academy': 901808675030,
        'spanish': 901808675033,
        'extra income': 901807369175,
        'personal': 901805493143,
        'tony fc': 901805493148,
        'test': 901811795053,
        'thai academy': 1100230000001825
    }

    # GET CLICKUP TASKS #
    url = "https://api.clickup.com/api/v2/list/{}/task?include_closed=true"

    headers = {
        "accept": "application/json",
        "Authorization": "pk_276666839_56HQ3ZATAKRPDWP7BZXLTMKYRETN83ST"
    }

    clickup_tasks = []
    for list_id in lists.values():
        response = requests.get(url.format(list_id), headers=headers)
        clickup_tasks.extend(json.loads(response.text)['tasks'])

    return clickup_tasks

    # END GET CLICKUP TASKS #


def process_task(task):
    points = 10  # default
    points_in_description = re.search('\+(\d*)', task['description'])
    if points_in_description:
        points = int(points_in_description.groups(0)[0])
    else:  # points in custom field
        points = int(next((f.get('value', 10)
                           for f in task.get('custom_fields', []) if f.get('name') == 'points'), 10))

    processed_task = {
        'clickup_id': task['id'],
        'task_name': task['name'],
        'due_date': int(task['due_date'])/1000 if task['due_date'] else None,
        'date_done': int(task['date_done'])/1000 if task['date_done'] else None,
        'points': points,
    }

    return processed_task


def refresh():
    today = date.today()
    clickup_tasks = get_clickup_tasks()

    # Get all done tasks, and pending tasks with due date older than today
    clickup_tasks = [
        x for x in clickup_tasks
        if x.get("date_done") is not None
        or (
            x.get("due_date")
            and int(x["due_date"]) > 0
            and datetime.fromtimestamp(int(x["due_date"]) / 1000).date() < today
        )
    ]

    saved_tasks = get_saved_tasks(conn, cur)
    # saved_tasks = []
    ignore_ids_done = []
    ignore_ids_pending = []
    for task in saved_tasks:
        if task[DATE_DONE]:
            # If same task id is done and saved, or if same task id is not done but was already saved today, then ignore id
            ignore_ids_done.append(task[CLICKUP_ID])

    for task in saved_tasks:
        if not task[DATE_DONE] and task[DATE_ADDED].date() == today:
            # If same task id is done and saved, or if same task id is not done but was already saved today, then ignore id
            ignore_ids_pending.append(task[CLICKUP_ID])

    for task in clickup_tasks:
        processed_task = process_task(task)
        # Check if task is done, or if task is pending. And if it was not saved before
        if (processed_task['date_done'] and not processed_task['clickup_id'] in ignore_ids_done) or (not processed_task['date_done'] and not processed_task['clickup_id'] in ignore_ids_pending):
            save_task(conn, cur, processed_task)

    conn.commit()


def calculate_points():
    levels = [0, 150, 1000, 3000, 5000, 20000]
    max_hps = [50, 100, 150, 200, 250]
    hp = 50
    xp = 0
    saved_active_tasks = get_saved_active_tasks(conn, cur)
    last_reset = get_last_reset(conn, cur)
    today = datetime.now()

    print("last reset:", last_reset)

    # recover hp by day
    daily_hp = 20
    days_passed = (today.date() - last_reset.date()).days

    # get max hp for the corresponding level
    def get_max_hp(xp):
        for i, level_xp in enumerate(levels[1:]):
            if xp < level_xp:
                return max_hps[i]
        return max_hps[-1]

    for delta_day in range(days_passed, -1, -1):
        print(delta_day)
        max_hp = get_max_hp(xp)
        current_day = (today - timedelta(days=delta_day)).date()
        print(f'> Current day is {current_day}')

        for task in list(filter(lambda task: task[DATE_DONE] and task[DATE_DONE].date() == current_day, saved_active_tasks)):
            # GET DONE TASKS TO ADD XP. DONE TASKS ON SAME DAY THAN THE CURRENT DAY IN THE ITERATION.
            xp += task[POINTS]

        for task in list(filter(lambda task: (not task[DATE_DONE]) and
                                (current_day - task[DUE_DATE].date()).days == 1, saved_active_tasks)):
            # GET NOT DONE TASKS TO DECREASE HP. TASKS ARE ADDED IN THE SYSTEM CONTINOUSLY WHEN NOT DONE.
            # SO WILL DISCOUNT HP ONLY WHEN THE SELECTED TASK WAS DUE FOR PREVIOUS DAY THAN CURRENT DAY IN THE ITERATION.
            print('----------------')
            print(task)
            # xp -= min(task[POINTS] * 1, 20)
            hp -= min(task[POINTS] * 2, 20)
            print('removing', min(task[POINTS] * 2, 20), 'hp')
            print('----------------')

        print("hp:", hp)
        print("xp:", xp)

        # RESET DIGIMON AFTER CHECKING TASKS
        if hp <= 0:
            insert_reset(conn, cur)
            return calculate_points()

        # INCREASE DAILY HP AFTER CHECKING PENDING TASKS
        if not current_day == last_reset.date():
            hp += daily_hp
            if hp > max_hp:
                hp = max_hp

        print("hp:", hp)
        print("xp:", xp)

        max_hp = get_max_hp(xp)

    print(f'HP is {hp}')
    print(f'XP is {xp}')
    current_level = 0
    for level, level_xp in enumerate(levels):
        if xp < 0:
            current_level = 0
            break
        elif xp >= level_xp:
            current_level = level
    print(f'Level is {current_level}')

    max_xp = levels[current_level+1]

    return current_level, hp, xp, max_xp, max_hp


def set_wallpaper(current_level, hp, xp, max_xp, max_hp):
    last_reset = get_last_reset(conn, cur)

    # Lista de imágenes base
    image_paths = [
        '/home/mauricio/github/digimon/wallpapers/koromon.png',
        '/home/mauricio/github/digimon/wallpapers/agumon.png',
        '/home/mauricio/github/digimon/wallpapers/greymon.png',
        '/home/mauricio/github/digimon/wallpapers/metal_greymon.png',
        '/home/mauricio/github/digimon/wallpapers/war_greymon.png',
    ]

    base_image = image_paths[current_level]
    if not os.path.isfile(base_image):
        print(f"File does not exist: {base_image}")
        return

    # Crear copia temporal para dibujar stats
    temp_image = f"/home/mauricio/github/digimon/wallpapers/tmp_wallpaper.jpg"
    img = Image.open(base_image).convert("RGB")
    draw = ImageDraw.Draw(img)

    # Tamaño de fuente relativo a la altura de la imagen
    # mínimo 20 para no ser demasiado pequeño
    font_size = max(15, int(img.height * 0.04))
    font = ImageFont.truetype(
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size
    )

    margin_x = int(img.width * 0.3555)
    margin_y = int(img.height * 0.79)

    bar_width = int(img.width * 0.2833)
    bar_height = font_size

    def draw_bar(draw, x, y, current, maximum, bar_color, bg_color="gray"):

        # Barra de fondo
        draw.rectangle([x, y, x + bar_width, y + bar_height], fill=bg_color)
        # Barra actual
        filled_width = int(bar_width * current / maximum)
        draw.rectangle([x, y, x + filled_width, y +
                       bar_height], fill=bar_color)
        # Número centrado
        text = f"{current}/{maximum}"
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        text_x = x + (bar_width - text_width) / 2
        text_y = y + (bar_height - text_height) / 2 - 3
        draw.text((text_x, text_y), text, fill="white", font=font)

    # draw date of birth (last reset)
    dob_font_size = max(10, int(img.height * 0.02))
    dob_font = ImageFont.truetype(
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", dob_font_size
    )
    dob_x = margin_x + bar_width - 90
    dob_y = 100
    draw.text((dob_x, dob_y), datetime.strftime(
        last_reset, "%d/%m/%Y"), fill="white", font=dob_font)

    # Dibujar HP
    hp = max(0, hp)
    draw_bar(draw, margin_x, margin_y, hp, max_hp, bar_color="red")
    # Dibujar XP debajo
    xp = max(0, xp)
    draw_bar(draw, margin_x, margin_y + bar_height +
             5, xp, max_xp, bar_color="cyan")

    # Guardar y establecer wallpaper
    img.save(temp_image)
    command = f"gsettings set org.gnome.desktop.background picture-uri 'file://{temp_image}'"
    os.system(command)
    print(f"Wallpaper set to: {temp_image}")


def get_tasks_for_calendar():
    now = datetime.now()

    tasks = get_clickup_tasks()
    # filter spanish classes tasks
    tasks = filter(lambda x: x['list']['id'] == '901808675033', tasks)

    # filter actual classes
    regex = re.compile(
        r'\b((?:1[0-2]|0?[1-9])(?:[:\.][0-5][0-9])?)\s?(am|pm)\b',
        re.IGNORECASE
    )
    tasks = list(filter(lambda x: regex.search(x['name']), tasks))
    # get and format task dates
    for task in tasks:

        task['new_datetime'] = None

        try:
            task['new_datetime'] = datetime.fromtimestamp(
                int(task['due_date']) / 1000)
        except:
            # print(task['name'])
            # print(task)
            continue

        m = regex.search(task['name'])
        new_hours = m.group(1).split('.')[0].split(':')[0]
        new_minutes = m.group(1).split('.')[1] if (
            len(m.group(1).split('.')) > 1) else 0
        am_pm = m.group(2)
        new_hours = int(new_hours)
        if new_hours == 12 and am_pm == 'pm':
            new_hours = 12
        elif am_pm == 'pm':
            new_hours += 12

        task['new_datetime'] = task['new_datetime'].replace(
            hour=int(new_hours), minute=int(new_minutes), second=0)

    # filter only future classes
    tasks = list(filter(lambda x: x['new_datetime'] is not None, tasks))
    tasks = list(filter(lambda x: x['new_datetime'] >= now, tasks))

    return tasks


def sync_google_calendar():
    tasks = get_tasks_for_calendar()
    for task in tasks:
        print(task['new_datetime'])

    service = get_calendar_service()

    remove_future_events(service)

    for task in tasks:
        print('Adding', task['name'], task['new_datetime'])
        add_event(service, task['name'], task['new_datetime'])


try:
    if len(sys.argv) < 2 or sys.argv[1] == 'refresh':
        refresh()
    if len(sys.argv) < 2 or sys.argv[1] == 'calculate':
        current_level, hp, xp, max_xp, max_hp = calculate_points()
        set_wallpaper(current_level, hp, xp, max_xp, max_hp)
    if len(sys.argv) > 2:
        if sys.argv[1] == 'reset':
            insert_reset(conn, cur)
except Exception as e:
    print(e)
finally:
    # Close cursor and connection
    if cur and conn:
        cur.close()
        conn.close()


# try:
#     sync_google_calendar()
# except Exception as e:
#     print("Calendar sync failed")
#     print(e)
#     traceback.print_exc()
