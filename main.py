from PIL import Image, ImageDraw, ImageFont
import requests
import json
from datetime import datetime, date
import psycopg2
import sys
import os

# DB columns

print('\n\n', datetime.now())

ID = 0
CLICKUP_ID = 1
DATE_ADDED = 2
TASK_NAME = 3
DUE_DATE = 4
DATE_DONE = 5
POINTS = 6


def connect_to_db():
    # DATABASE
    # Create a connection
    conn = psycopg2.connect(
        user="postgres",
        password="postgres",
        host="192.168.1.131",
        port=5432,
        database="digimon"
    )

    # Create a cursor to execute queries
    cur = conn.cursor()
    # END DATABASE

    return conn, cur


conn, cur = connect_to_db()


def get_saved_tasks(conn, cur):

    # Example query
    cur.execute("SELECT * FROM tasks;")
    saved_tasks = cur.fetchall()

    return [list(row) for row in saved_tasks]


def get_saved_active_tasks(conn, cur):

    # Example query
    cur.execute("""SELECT *
        FROM tasks
        WHERE date_added > (
            SELECT MAX(datetime) FROM resets
        );""")
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
        'test': 901811795053
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
    processed_task = {
        'clickup_id': task['id'],
        'task_name': task['name'],
        'due_date': int(task['due_date'])/1000 if task['due_date'] else None,
        'date_done': int(task['date_done'])/1000 if task['date_done'] else None,
        # 10  # fix later
        'points': int(next((f.get('value', 10) for f in task.get('custom_fields', []) if f.get('name') == 'points'), 10)),
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
    levels = [0, 150, 1000, 3000, 5000]
    hp = 100
    xp = 0
    saved_active_tasks = get_saved_active_tasks(conn, cur)
    last_reset = get_last_reset(conn, cur)
    today = datetime.now()

    for task in saved_active_tasks:
        if task[DATE_DONE]:
            xp += task[POINTS]
        else:
            xp -= min(task[POINTS] * 3, 20)
            hp -= min(task[POINTS] * 3, 20)

    # recover hp by day
    daily_hp = 10
    days_passed = (today.date() - last_reset.date()).days
    hp += daily_hp * days_passed

    if hp < 0:
        insert_reset(conn, cur)
    elif hp > 100:
        hp = 100

    print(f'HP is {hp}')
    print(f'XP is {xp}')
    current_level = 0
    for level, level_xp in enumerate(levels):
        if xp >= level_xp:
            current_level = level
    print(f'Level is {current_level}')

    return current_level, hp, xp


def set_wallpaper(current_level, hp, xp):
    # Lista de imágenes base
    image_paths = [
        '/home/mauricio/github/digimon/wallpapers/koromon.jpg',
        '/home/mauricio/github/digimon/wallpapers/agumon.jpg',
        '/home/mauricio/github/digimon/wallpapers/greymon.jpg',
        '/home/mauricio/github/digimon/wallpapers/metal_greymon.jpg',
        '/home/mauricio/github/digimon/wallpapers/war_greymon.jpg',
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
    font_size = max(20, int(img.height * 0.05))
    font = ImageFont.truetype(
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size
    )

    # Márgenes desde el borde superior izquierdo
    margin_x = int(img.width * 0.06)  # 3% del ancho
    margin_y = int(img.height * 0.30)  # 3% del alto

    # Dibujar HP y XP
    draw.text((margin_x, margin_y), f"HP: {hp}", fill="red", font=font)
    draw.text((margin_x, margin_y + font_size + 5),
              f"XP: {xp}", fill="blue", font=font)

    # Guardar y establecer wallpaper
    img.save(temp_image)
    command = f"gsettings set org.gnome.desktop.background picture-uri 'file://{temp_image}'"
    os.system(command)
    print(f"Wallpaper set to: {temp_image}")


try:
    if len(sys.argv) < 2 or sys.argv[1] == 'refresh':
        refresh()
    if len(sys.argv) < 2 or sys.argv[1] == 'calculate':
        current_level, hp, xp = calculate_points()
        set_wallpaper(current_level, hp, xp)
except Exception as e:
    print(e)
finally:
    # Close cursor and connection
    cur.close()
    conn.close()
