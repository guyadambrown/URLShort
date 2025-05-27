from flask import Flask, request, jsonify, redirect
import mysql.connector
import json
import string
import random
import threading

# Load settings from a JSON file
with open("settings.json", "r") as settings_file:
    settings = json.load(settings_file)
    print("Settings loaded")
    print(settings)


def connect_to_db():
    # Connect to MySQL database
    db_config = settings['database']
    if db_config['type'] != 'mysql':
        raise ValueError("Unsupported database engine. Only MySQL is supported.")
    else:
        if db_config['type'] == 'mysql':
            connection = mysql.connector.connect(
                host=db_config['host'],
                user=db_config['user'],
                password=db_config['password'],
                database=db_config['name']
            )
            return connection


def create_table_if_not_exists():
    print("Creating table")
    connection = connect_to_db()
    cursor = connection.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS urls (
            id INT AUTO_INCREMENT PRIMARY KEY,
            original_url VARCHAR(255) NOT NULL,
            short_url VARCHAR(10) NOT NULL UNIQUE
        )
    """)
    connection.commit()
    cursor.close()
    connection.close()


def check_url_exists(short_url):
    connection = connect_to_db()
    cursor = connection.cursor()
    cursor.execute("SELECT * FROM urls WHERE short_url = %s", (short_url,))
    exists = cursor.fetchone() is not None
    cursor.close()
    connection.close()
    return exists


def add_url(original_url, short_url):
    connection = connect_to_db()
    cursor = connection.cursor()
    cursor.execute("INSERT INTO urls (original_url, short_url) VALUES (%s, %s)", (original_url, short_url))
    connection.commit()
    cursor.close()
    connection.close()


def get_original_url(short_url):
    connection = connect_to_db()
    cursor = connection.cursor()
    cursor.execute("SELECT original_url FROM urls WHERE short_url = %s", (short_url,))
    result = cursor.fetchone()
    cursor.close()
    connection.close()
    if result is None:
        return None
    else:
        return result[0]

app = Flask(__name__)
# Create the database table if it does not exist
create_table_if_not_exists()

@app.route('/')
def hello_world():  # put application's code here
    # Check connection to the database
    try:
        connection = connect_to_db()
        connection.close()
        return "Hello, World! Database connection successful!"
    except mysql.connector.Error as err:
        return f"Error: {err}"


@app.route('/shorten', methods=['POST'])
def shorten_url():
    # Allow the user to specify the short URL
    custom_short_url = request.json.get('custom_short_url')
    original_url = request.json.get('original_url')
    if not original_url:
        return jsonify({"error": "Original URL is required"}), 400
    if custom_short_url:
        if len(custom_short_url) > 10 or not custom_short_url.isalnum():
            return jsonify({"error": "Custom short URL must be alphanumeric and up to 10 characters long"}), 400
        # Check if the custom short URL already exists
        if check_url_exists(custom_short_url):
            return jsonify({"error": "Custom short URL already exists"}), 400
        # Add the URL to the database
        add_url(original_url, custom_short_url)
        return jsonify({"short_url": custom_short_url}), 201
    else:
        # Generate a random short URL
        while True:
            custom_short_url = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
            if not check_url_exists(custom_short_url):
                break
        add_url(original_url, custom_short_url)
        return jsonify({"short_url": custom_short_url}), 201
@app.route('/<short_url>', methods=['GET'])

def redirect_to_url(short_url):
    original_url = get_original_url(short_url)
    if original_url is None:
        return jsonify({"error": "Short URL not found"}), 404
    else:
        # Redirect to the original URL
        return redirect(original_url, code=302)


def run_flask():
    app.run(host=settings['server']['host'], port=settings['server']['port'])

if __name__ == '__main__':
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()
    if settings['discord']['enabled']:
        import discord
        from discord.ext import commands

        # Initialize Discord bot
        intents = discord.Intents.default()
        intents.message_content = True
        client = discord.Client(intents=intents)
        tree = discord.app_commands.CommandTree(client)

        def create_error_embed(description):
            return discord.Embed(title="Error", description=description, color=discord.Color.red())

        def create_success_embed(description):
            return discord.Embed(title="Success", description=description, color=discord.Color.green())


        # Command to shorten URL
        @tree.command(name='shorten', description='Shorten a URL',
                      guilds=[discord.Object(id=settings['discord']['guild_id'])])
        async def shorten(interaction: discord.Interaction, original_url: str, custom_url: str = None):
            await interaction.response.defer(ephemeral=False)
            if not original_url:
                await interaction.followup.send(embed=create_success_embed('URL not provided'), ephemeral=False)
                return
            if not original_url.startswith(('http://', 'https://')):
                await interaction.followup.send(embed=create_error_embed('URL must start with http:// or https://'), ephemeral=False)
                return
            if custom_url:
                if len(custom_url) > 10 or not custom_url.isalnum():
                    await interaction.followup.send(embed=create_success_embed("Custom short URL must be alphanumeric and up to 10 characters long"), ephemeral=False)
                    return
                if check_url_exists(custom_url):
                    await interaction.followup.send(embed=create_error_embed("Custom URL already exists"), ephemeral=False)
                    return
                add_url(original_url, custom_url)
                await interaction.followup.send(embed=create_success_embed(f"URL: {settings['shortener']['base_url']}/{custom_url}"), ephemeral=False)
            else:
                while True:
                    custom_url = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
                    if not check_url_exists(custom_url):
                        break
                add_url(original_url, custom_url)
                await interaction.followup.send(embed=create_success_embed(f"URL: {settings['shortener']['base_url']}/{custom_url}"), ephemeral=False)


        @client.event
        async def on_ready():
            print(f'Connected to discord as {client.user} (ID: {client.user.id})')
            # Sync the command tree to the testing guild
            await tree.sync(guild=discord.Object(id=settings['discord']['guild_id']))


        client.run(settings['discord']['bot_token'])

