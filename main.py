import discord
from discord.ext import commands
from discord.ui import Button, View
import pymongo
import os
import random

# MongoDB setup
client = pymongo.MongoClient(
    "mongodb+srv://binod_123:123@discordgame.rytu8w9.mongodb.net/?retryWrites=true&w=majority&appName=discordgame"
)
db = client['discord_bot']
users_collection = db['users']
games_collection = db['games']

# Discord bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)


# Helper functions for MongoDB
def get_user_points(user_id):
    user = users_collection.find_one({"_id": user_id})
    if user:
        return user['points']
    else:
        return 0


def set_user_points(user_id, points):
    users_collection.update_one({"_id": user_id}, {"$set": {
        "points": points
    }},
                                upsert=True)


def add_user_points(user_id, points):
    users_collection.update_one({"_id": user_id}, {"$inc": {
        "points": points
    }},
                                upsert=True)
    return get_user_points(user_id)  # Return the new point total


def remove_user_points(user_id, points):
    users_collection.update_one({"_id": user_id},
                                {"$inc": {
                                    "points": -points
                                }},
                                upsert=True)
    return get_user_points(user_id)  # Return the new point total


def save_game_state(game_state):
    # Convert all keys in the 'votes' dictionary to strings
    game_state['votes'] = {
        str(key): value
        for key, value in game_state['votes'].items()
    }
    games_collection.update_one({"_id": 1}, {"$set": game_state}, upsert=True)


def get_game_state():
    game_state = games_collection.find_one({"_id": 1})
    if game_state:
        # Convert all keys in the 'votes' dictionary back to integers
        game_state['votes'] = {
            int(key): value
            for key, value in game_state['votes'].items()
        }
    return game_state


def clear_game_state():
    games_collection.delete_one({"_id": 1})


# Command Handlers
@bot.command(name='startgame')
@commands.has_any_role('admin', 'pointmanager')
async def start_game(ctx):
    game_state = {"_id": 1, "active": True, "votes": {}}
    save_game_state(game_state)

    class VoteView(View):

        def __init__(self):
            super().__init__(timeout=None)
            self.voted_users = set()  # Keep track of users who have voted

        @discord.ui.button(label='Red', style=discord.ButtonStyle.danger)
        async def red_button(self, interaction: discord.Interaction,
                             button: discord.ui.Button):
            await self.handle_vote(interaction, 'red')

        @discord.ui.button(label='Green', style=discord.ButtonStyle.success)
        async def green_button(self, interaction: discord.Interaction,
                               button: discord.ui.Button):
            await self.handle_vote(interaction, 'green')

        @discord.ui.button(label='Blue', style=discord.ButtonStyle.primary)
        async def blue_button(self, interaction: discord.Interaction,
                              button: discord.ui.Button):
            await self.handle_vote(interaction, 'blue')

        async def handle_vote(self, interaction: discord.Interaction,
                              color: str):
            user_id = interaction.user.id
            game_state = get_game_state()

            if not game_state or not game_state['active']:
                await interaction.response.send_message("No game is active.",
                                                        ephemeral=True)
                return

            if get_user_points(user_id) < 50:
                await interaction.response.send_message(
                    "You don't have enough points to vote.", ephemeral=True)
                return

            if user_id in self.voted_users:
                await interaction.response.send_message(
                    "You have already voted.", ephemeral=True)
                return

            # Deduct points and save the vote
            remove_user_points(user_id, 50)
            total_points = get_user_points(user_id)
            game_state['votes'][str(user_id)] = color
            self.voted_users.add(user_id)  # Mark this user as having voted
            save_game_state(game_state)

            # Create a new VoteView instance for the updated view
            updated_view = VoteView()
            updated_view.voted_users = self.voted_users.copy()  # Transfer voted users to new view

            # Disable buttons only for users who have voted
            

            # Send an ephemeral response to the user who voted
            await interaction.response.send_message(
                f"You voted for {color}. 50 points deducted. Your total points: {total_points}",
                ephemeral=True)

            # Edit the original message to update the view without changing the main content
            await interaction.message.edit(view=updated_view)

    await ctx.send(f"Game has started! Choose your color:@everyone\n\n", view=VoteView())


@bot.command(name='addpoint')
@commands.has_any_role('admin', 'pointmanager')
async def set_point(ctx, user: discord.Member, points: int):
    new_points = add_user_points(user.id, points)
    await ctx.send(
        f"Added {points} points to {user.mention}: New points {new_points}")


@bot.command(name='removepoint')
@commands.has_any_role('admin', 'pointmanager')
async def remove_point(ctx, user: discord.Member, points: int):
    new_points = remove_user_points(user.id, points)
    await ctx.send(
        f"Removed {points} points from {user.mention}: New points {new_points}"
    )


@bot.command(name='point')
async def check_point(ctx, user: discord.Member):
    points = get_user_points(user.id)
    await ctx.send(f"{user.mention} has {points} points")


@bot.command(name='allpoint')
@commands.has_any_role('admin', 'pointmanager')
async def all_point(ctx, *users: discord.Member):
    total_with_points = 0
    total_without_points = 0
    response = ""

    for user in users:
        points = get_user_points(user.id)
        response += f"{user.mention} points: {points}\n"
        if points > 0:
            total_with_points += 1
        else:
            total_without_points += 1

    response += f"\nTotal users with points: {total_with_points}\n"
    response += f"Total users without points: {total_without_points}"

    await ctx.send(response)


@bot.command(name='endgame')
@commands.has_any_role('admin', 'pointmanager')
async def end_game(ctx):
    game_state = get_game_state()
    if not game_state or not game_state['active']:
        await ctx.send("No game is currently active.")
        return

    game_state['active'] = False
    save_game_state(game_state)

    # Count votes for each color
    red_votes = sum(1 for vote in game_state['votes'].values() if vote == 'red')
    green_votes = sum(1 for vote in game_state['votes'].values() if vote == 'green')
    blue_votes = sum(1 for vote in game_state['votes'].values() if vote == 'blue')

    vote_counts = {'red': red_votes, 'green': green_votes, 'blue': blue_votes}
    min_votes = min(vote_counts.values())

    # Determine winning color(s) - color(s) with least votes
    winning_colors = [color for color, votes in vote_counts.items() if votes == min_votes]

    if len(winning_colors) == 3:
        # All colors are tied
        winning_color = random.choice(winning_colors)
    elif len(winning_colors) == 2:
        # Two colors are tied
        winning_color = random.choice(winning_colors)
    else:
        # Single color with least votes
        winning_color = winning_colors[0]

    losing_colors = [color for color in vote_counts if color != winning_color]

    # Identify losers and winners based on the colors
    losers = [user_id for user_id, color in game_state['votes'].items() if color in losing_colors]
    winners = [user_id for user_id, color in game_state['votes'].items() if color == winning_color]

    # Award 100 points to winners
    for winner in winners:
        add_user_points(int(winner), 100)

    # Prepare the result message
    losing_color_str = ', '.join(losing_colors).capitalize()
    winners_mentions = ', '.join([f'<@{user_id}>' for user_id in winners])

    result_message = (
        f" **Game Over!** \n"
        f"**Users voted : {losing_color_str} : lost **\n\n"
        f"Users who voted for {winning_color} won and earned **100 points**!\n"
        f"**Winners**: {winners_mentions if winners else 'No winners'}"
    )
    await ctx.send(result_message)
    clear_game_state()


# Running the bot
bot.run('MTI3MDc1OTA0NzM4MDg2MDk0MA.Gf1R5M.KVxkZAivRCDB1z-AxGQ61FVg8h2JxD_YL1ZQRM')
