#!/usr/bin/python
"Parses OpenArena/Quake3 logs and writes game statistics to HTML files."

#   pyqscore. Parse OpenArena/Quake3 logs and write statistics to HTML.
#   Copyright (C) 2011  Jose Rodriguez
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation, version 2.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License
#   along with this program.  If not, see <http://www.gnu.org/licenses/>.

__author__    = "Jose Rodriguez"
__version__   = "1.0.1"
__date__      = "19-11-2015"
__license__   = "GPLv2"
__copyright__ = "Copyright (C) 2011  Jose Rodriguez"


import sys
import os
import shutil
import re
import json
import cPickle
import webbrowser
import Tkinter as Tk
import tkFileDialog
from operator import mod
from datetime import timedelta, datetime
from random import randint


#=======================         OPTIONS         ======================= #

TK_WINDOW = True
# Launch a Tkinter open file dialog to input log file (True/False)

MOVE_HTML_OUTPUT = True
# If True, the output file will be moved to directory html_files
# This may be convenient for some people, as it will avoid problems
# with the CSS file and icons missing.

MAXPLAYERS = 150
# Maximum number of players displayed in HTML output

SORT_OPTION = 'time'
# How to sort table columns. Options: deaths, frag_death_ratio,
# frags, games, ping, time, won, won_percentage

BAN_LIST = [ 'UnnamedPlayer', 'a_player_I_dont_like' ]
# Comma-separated list containing the nicks of undesired players.
# Nicks must include the colour codes and be inside quotes. 

MINPLAY = 0.5
# From 0 to 1, minimum fraction of time a player has to play in a game
# relative to that of the player who played for longer in order appear
# in the statistics. Example: Player A is the first player joining a
# match. The match lasts for 10 minutes. If MINPLAY is 0.7, only the
# statistics of players who joined during the first 3 minutes will count.

NUMBER_OF_QUOTES = 5
# Number of random quotes displayed

OPEN_BROWSER = True
# Open browser when finished (True/False)

DUMP_DATA = ''
# Dump processed data to file in JSON format by setting this to 'yes'

GTYPE_OVERRIDE = ''
# If you have a mixed log with different game types, this will override
# the game type read from the log. You can type what you want here.

DISPLAY_CTF_TABLE = True
# Display or not the CTF table in the HTML output. This will only work
# if there are players with CTF-related data (True/False)


# ====================================================================== #


class Game:
    '''Class with no methods used to store game data.'''
    def __init__(self,number):
        self.number = number            # game number
        self.mapname  = []
        self.players  = {}              # nick: (ping, position)   
        self.pid      = {}              # player id
        self.handicap = {}
        self.teams    = {}
        self.scores   = []
        self.awards   = {}
        self.itemsp   = {}
        self.killsp   = {}             # world frags and suicides
        self.deathsp  = {}             # deaths caused by other players
        self.ctf      = {}             # 0: flag taken; 1: capture
                                       # 2:flag return; 3: flag fragged
        self.killsp['<world>'] = []
        self.ptime    = {}             # Player time
        self.time     = 0              # Game time 
        self.validp   = []             # Valid game flag
        self.quotes   = set()
        self.weapons  = {}


class Server:
    '''Another class to store server data.'''
    def __init__(self):
        #self.name  = server_name
        self.time  = 0
        self.frags = 0
        self.gtype = 0


def check_args(log_file=None):
    '''Checks arguments and existence of input file, returns it if OK'''
    if log_file is None:
        argv = sys.argv
        if len(argv) < 2:
            print '\nPlease specify log file to be processed.\n'
            raise SystemExit
        else:
            log_file = argv[1]
    try:
        file_in = open(log_file, 'r')
    except(IOError):
        print '\nCould not open log file. Exiting...\n'
        raise SystemExit
    else:            
        file_in.close()
    return log_file


def check_cache(log_file):
    '''Checks cache file.
    
    Returns
    -------
    cache: unpickled cache (empty if cache not present)
    
    Cache files are simple pickled Python lists that store data from 
    previously processed log files. They speed up the processing time greatly.
    
    The last elements of the cache store some needed metadata:
    
    - position [-1]: size in bytes of the log file from the previous run
    - position [-2]: number of lines read from log up to the previous run
    - position [-3]: a Server() instance with accumulated server data
    - position [-3]: accumulated list of unique quotes
    
    The rest of the elements store accumulated player data.
    
    The size of the log file is checked every run, and if found to be smaller 
    than what the cache file indicates, it is assumed that the log has been 
    overwritten and the cache is discarded.
    '''    
    cache_file = str(log_file[:-4]) + '_cache.p'
    cache = []
    try:
        cache = cPickle.load(open(cache_file, 'rb'))
    except(IOError):
        print '\nNo cache file found. Will process the entire log file.'
        cache_present = False
    else:
        if os.path.getsize(log_file) < cache[-1][1]:
            print '\nLog file size is smaller than the cached one!'
            print 'Processing the entire log file.\n'
            cache_present = False
        else:
            N = cache[-2][1]      # lines read stored at position [-2]
            print '\nCache file found!\n' + str(N) + ' lines already processed'
            cache_present = True
    return cache


def read_log(log_file, cache=[]):
    '''Reads log file and outputs dictionary storing lines.
    
    If cache file is present only new lines are considered'''
    if len(cache) != 0:
        Nlines = cache[-1][1]
    else:
        Nlines = 1

    log = {}
    count = 1
    k_new = 0

    with open(log_file, 'r') as f:
        for line in f:
            if count < Nlines:
                # Ignore lines from previous runs
                pass
            else:
                log[count] = line
                k_new += 1
            count += 1
    print  '\n' + str(k_new) + ' new lines read.\n'
    return log, count


def mainProcessing(log):
    '''Main processing function'''
    server = Server()
    cgames = []              # Cumulative list of games: instances of Game()
    N = 1                    # Game number
    lines = (line for line in log.values())
    for line in lines:
        if line.find(' InitGame: ') > 0 and lines.next().find(' Warmup:') == -1:
            # New game started (no warmup). Begin to parse stuff
            game = Game(N)
            N += 1
            game.pos = 1          # Player's score position
            game, server = lineProcInit(line, game, server)
            game, server, valid_game = oneGameProc(lines, game, server)
            if valid_game == True:
                if len(game.players) == 0:
                    continue
                server.time = server.time + game.time - min(game.ptime.values())
                cgames.append(game)               # Append game to list of games
    return server, cgames


def lineProcInit(line, game, server):
    '''Process game init lines'''
    #  0:00 InitGame: \capturelimit\0\g_maxGameClients\0\sv_maxclients\8\timelimit\0\fraglimit\20\dmflags\0\sv_hostname\noname\sv_minRate\0\sv_maxRate\0\sv_minPing\0\sv_maxPing\0\sv_floodProtect\1\sv_allowDownload\1\version\ioQ3 1.33+oa linux-i386 Jul  7 2007\g_gametype\0\protocol\68\mapname\foxhill\sv_privateClients\0\gamename\baseoa\g_needpass\0
        
    #  0:00 InitGame: \dmflags\0\fraglimit\20\timelimit\12\g_gametype\0\sv_privateClients\6\sv_hostname\^1SUPERCOOLSERVER!!!! \sv_maxclients\4\sv_minRate\0\sv_maxRate\25000\sv_minPing\0\sv_maxPing\500\sv_floodProtect\1\sv_allowDownload\1\sv_dlURL\http://server/path\g_maxGameClients\22\capturelimit\8\g_delagHitscan\1\g_obeliskRespawnDelay\10\elimination_roundtime\90\elimination_ctf_oneway\0\version\ioq3+oa 1.35 linux-i386 Oct 20 2008\protocol\71\mapname\13base\.Admin\My name\.e-mail\My email\.Location\My location\.OS\My OS\gamename\baseoa\g_needpass\0\g_rockets\0\g_instantgib\0\g_humanplayers\0
    
    #  0:00 InitGame: \g_delagHitscan\1\sv_hostname\noname\sv_minRate\0\sv_maxRate\0\sv_minPing\0\sv_maxPing\0\sv_floodProtect\1\dmflags\0\fraglimit\20\timelimit\0\sv_maxclients\6\g_maxGameClients\0\capturelimit\0\g_allowVote\1\g_voteGametypes\/0/1/3/4/5/6/7/8/9/10/11/12/\g_voteMaxTimelimit\0\g_voteMinTimelimit\0\g_voteMaxFraglimit\0\g_voteMinFraglimit\0\elimination_roundtime\120\g_lms_mode\0\videoflags\7\g_doWarmup\0\version\ioQ3 1.33+oa linux-i386 Oct 22 2008\g_gametype\0\protocol\71\mapname\ce1m7\sv_privateClients\0\sv_allowDownload\0\g_instantgib\0\g_rockets\0\gamename\baseoa\elimflags\0\voteflags\0\g_needpass\0\g_obeliskRespawnDelay\10\g_enableDust\0\g_enableBreath\0\g_altExcellent\0
    regex = re.compile('mapname[\\\\]([\w]*)')
    mapname = regex.search(line).group(1)
    game.mapname = mapname
    
    idx = line.find('sv_hostname') + 11
    hostname = line[idx:idx+50].split('\\')[1]  # Does this always work?
    server.hostname = hostname                  # I hope so anyway
    
    idx = line.find('g_gametype')
    game.gametype = line[idx+11]
    try:
        server.gtype = int(game.gametype)
    except(ValueError):
        server.gtype = 0              # Default to DM if bad things happen    
    return game, server

        
def oneGameProc(lines, game, server):
    '''Process lines from one single game'''
    valid_game = False
    for line in lines:
        # Process more frequent lines first: Items >> Kill > Userinfo > Awards
        if line.find(' Item: ') > 0:
            # I don't need items at the moment, so pass and save a lot of time.
            # If they are needed the following function provide everything 
            # required to keep track of the items collected by each player.
            #game = lineProcItems(line, game)
            continue
        elif line.find(' Kill: ') > 0:        
            game, server = lineProcKills(line, game, server)
        elif line.find(' CTF: ') > 0:
            game = lineProcCTF(line, game)
        elif line.find(' Award: ') > 0:
            game = lineProcAwards(line, game)            
        elif line.find('UserinfoChanged') > 0:
            game = lineProcUserInfo(line, game)
        elif line.find(' say:') > 0:
            game = lineProcQuotes(line, game)
        elif line.find(' score: ') > 0:
            game = lineProcScores(line, game)
        elif line.find(' red:') > 0:
            # 20:33 red:4  blue:5
            game.ctfscores = (line[11], line[19])
        elif ((line.find('Exit: Timelimit hit') > 0) or      
              (line.find('Exit: Fraglimit hit') > 0) or    
              (line.find('Exit: Capturelimit hit') > 0)):
            # Game completed. Make a note of the time and flag it as valid.
            e_idx = line.find('Exit')
            game.time = totime(line[0:e_idx])
            valid_game = True
        elif line.find(' ShutdownGame:') > 0:
            break
    return game, server, valid_game


def lineProcItems(line, game):
    '''Process item lines'''
    #  0:35 Item: 1 ammo_lightning
    #100:22 Item: 0 item_health
    parts  = this_line[13:].split(' ')
    client = parts[0]
    item   = parts[1][:-1]
    # try/except clause to avoid rare cases of damaged logs. 
    # Items assigned to player who currently owns specified id.
    # In case of client disconnection this may give an erroneous 
    # count, a circumstance minimised by only storing players with
    # a minimum playing time. See game.validp in lineProcScores().
    try:
        game.itemsp[game.pid[client]].append(item)
    except:
        pass
    return game


def lineProcKills(this_line, game, server):
    '''Process kill lines'''
    #  3:20 Kill: 3 2 10: Gargoyle killed Gargoyle by MOD_RAILGUN
    #100:04 Kill: 0 1 11: ^4kernel panic killed Kyonshi by MOD_PLASMA
    k_idx  = this_line.find(' killed ')
    # If somebody's nick contains the string ' killed ',
    # we're screwed
                
    regex  = re.compile('\d:[\s](.*)')         # Fragger's nick
    try:
        # Does this really need a try/except clause?
        killer = regex.search(this_line[17:k_idx]).group(1)
    except:
        return game, server
                
    d_idx  = k_idx + 6
    b_idx  = this_line.rfind(' b')
    killed = this_line[d_idx + 2:b_idx]           # Victim
    weapon = this_line[b_idx + 7 + 1:-1]          # Weapon
    # try statement needed to avoid rare cases of damaged logs:
    # We're looking stuff up on a dictionary, so if the line is
    # broken the key may not exist and python complains
    try:
        if killer == killed:
            game.killsp[killer].append(weapon)
        elif killer != '<world>':
            game.weapons[killer][weapon[0:3]] = (
                                    game.weapons[killer][weapon[0:3]] + 1)
        else:
            game.killsp['<world>'].append(killed)
        game.deathsp[killed] = game.deathsp[killed] + 1
    except:
        pass
    else:
        server.frags += 1
    return game, server


def lineProcCTF(this_line, game):
    '''Process CTF lines'''
    #  9:40 CTF: 1 1 3: Inhakitor fragged RED's flag carrier!
    # 10:18 CTF: 3 1 0: Mynard Killman got the RED flag!
    p_id  = this_line[12]                         # Player ID
    #team  = this_line[14]                        # Useless datum
    event = this_line[16]              
    # 0: flag taken; 1: flag cap; 
    # 2: flag return; 3: flag carrier fragged
    try:
        game.ctf[game.pid[p_id]][event] = game.ctf[game.pid[p_id]][event] + 1
    except:
        pass
    return game


def lineProcAwards(this_line, game):
    '''Process line awards lines'''
    #  3:02 Award: 4 2: Grunt gained the IMPRESSIVE award!
    # 11:02 Award: 2 1: Kyonshi gained the EXCELLENT award!
    g_idx = this_line.find(' gained ')
    regex = re.compile('\d:\s(\S*\s?\S*)')        # Player name
    result = regex.search(this_line[0:g_idx])
    # Assist, Capture, Defence, Impressive, Excellent 
    name, award = [result.group(1), this_line[g_idx+12:g_idx+13]]
    try:
        game.awards[name][award] = game.awards[name][award] + 1
    except:
        pass
    return game


def lineProcUserInfo(this_line, game):
    '''Process user info lines'''
    #  0:05 ClientUserinfoChanged: 0 n\kernel\t\3\model\sarge/classic\hmodel\sarge/classic\g_redteam\\g_blueteam\\c1\3\c2\5\hc\100\w\0\l\0\tt\0\tl\0
    #103:22 ClientUserinfoChanged: 1 n\Kyonshi\t\0\model\kyonshi\hmodel\kyonshi\c1\4\c2\5\hc\100\w\0\l\0\skill\    5.00\tt\0\tl\0
    regex    = re.compile('Changed:[\s]([\d]*)')    # client id
    new_id   = regex.search(this_line).group(1)
    regex    = re.compile('n\\\\([^\\\\]*)')        # client name
    new_name = regex.search(this_line).group(1)
    try:
        regex    = re.compile('\\\\hc\\\\(\d*)')    # handicap
        handicap = regex.search(this_line).group(1)
    except:
        handicap = 100
    # Team. 0: free for all; 1: red; 2: blue; 3: spectator
    regex    = re.compile('\\\\t\\\\(\d)')    
    team     = regex.search(this_line).group(1)

    if new_name not in game.pid.values():
        # Initialize dictionaries for new player
        game.itemsp[new_name]   = []
        game.killsp[new_name]   = []
        game.deathsp[new_name]  = 0
        game.awards[new_name]   = {'A': 0, 'C': 0, 'D': 0, 'E': 0, 'I': 0 }
        game.handicap[new_name] = handicap
        game.teams[new_name]    = team
        game.ctf[new_name]      = {'0': 0, '1': 0, '2': 0, '3': 0}
        game.weapons[new_name]  = {'SHO': 0, 'GAU': 0, 'MAC': 0, 'GRE': 0, 
                                   'ROC': 0, 'PLA': 0, 'RAI': 0, 'LIG': 0, 
                                   'BFG': 0, 'TEL': 0, 'NAI': 0, 'CHA': 0 }
        
        c_idx = this_line.find('ClientU')
        game.ptime[new_name]    = totime(this_line[0:c_idx])
        # Keep track of player's current id
        game.pid[new_id] = new_name
    return game


def lineProcQuotes(this_line, game):
    '''Process quotes lines'''
    #  2:03 say: ^2ONAK: joder otra vez no
    name = this_line.split(':')[2]
    bs = this_line.split(':')[3][0:-1]
    game.quotes.add( (name,bs) )
    return game

        
def lineProcScores(this_line, game):
    '''Process scores lines'''
    #  5:40 score: 6  ping: 85  client: 2 Iagoi
    # 10:14 score: 12  ping: 62  client: 2 Iagoi
    regex = re.compile('(\s?\s?\s? \S*) [\s][^\s]*[\s] (\S?\d*) [\s]+[^\s]*[\s] (\d*) [\s]+[^\s]*[\s] (\d*) \s (.*)', re.VERBOSE)
    result = regex.search(this_line)
                
    [time, score, ping, client, nick] = [result.group(1), result.group(2),
                                         result.group(3), result.group(4),
                                         result.group(5)]
                
    game.scores.append([time, score, ping, client, nick])
    game.players[nick] = (ping, game.pos)
    game.pos += 1                   # Increase position for next player
    # Players are considered 'valid' if time played is greater than a 
    # percentage of the time played by the 1st player who joined the game. 
    # This: a) minimises the possibility of wrong item assignment due to 
    # multiple connections and disconnections; b) results in fairer statistics
    if (game.time - game.ptime[nick]) > MINPLAY * (game.time -
                                                   min(game.ptime.values())):
        game.validp.append(nick)
    return game


def totime(string):
    '''Convert strings of the format mmm:ss to an int of seconds'''
    mins, secs = string.split(':')
    time = timedelta(minutes = int(mins), seconds = int(secs)).seconds
    return time


def csum(A):
    """Column-wise addition of lists. Returns a list."""
    # Check whether A is multidimensional
    if type(A[0]) is not list and type(A[0]) is not tuple:
        S = A
        return S
    # Check that A is not jagged
    for row in A:
        if len(row) != len(A[0]):
            print "Not square..."
    # Do the damn summation cause Python can't be bothered to do it alone
    S = []
    for i in range(len(A[0])):
        S.append(sum([row[i] for row in A]))
    return S


def get_quotes(cgames):
    '''Create non repeating list of quotes from list of games.'''
    if len(cgames) != 0:
        quotes_list = [cgames[i].quotes for i in xrange(len(cgames)) if
                       cgames[i].quotes != []]
        quotes_list = list(set([item for sublist in quotes_list for 
                                item in sublist]))
    else:
        quotes_list = []
    return quotes_list


def allnames(cgames):
    """Return names of all valid players in log."""
    allnames = set()
    for game in cgames:
        allnames.update(game.validp)
    return allnames


def player_stats_total(cgames):
    """Get accumulated stats per player for all players in log.""" 
    all_players = []
    for name in allnames(cgames):
        win, time = 0, 0
        hand, ping, weapon_count, ctf_events = [], [], [], []
        frags, deaths, suics, wfrags = 0, 0, 0, 0
        awards_a, awards_c, awards_d, awards_e, awards_i = 0, 0, 0, 0, 0
        items = []
        for i in xrange(len(cgames)):
            if name not in cgames[i].validp:        # ignore no valid players
                pass
            else:
                game_stats = player_stats(cgames, i, name)
                win      = win      + game_stats[1]
                time     = time     + game_stats[2]
                hand.append(int(game_stats[3]))                
                ping.append(int(game_stats[4]))
                frags    = frags    + game_stats[5]
                deaths   = deaths   + game_stats[6]
                suics    = suics    + game_stats[7]
                wfrags   = wfrags   + game_stats[8]
                awards_a = awards_a + game_stats[9][0]
                awards_c = awards_c + game_stats[9][1]
                awards_d = awards_d + game_stats[9][2]
                awards_e = awards_e + game_stats[9][3]
                awards_i = awards_i + game_stats[9][4]
                weapon_count.append(game_stats[10])
                ctf_events.append(game_stats[11])
                #items.append(game_stats[12])
        if frags == 0:
            # Take rid of players with autodownload 'off' who 
            # appear to join the server momentarily.
            pass
        else:
            one_player = {'name':name,  'games':len(hand),  'won':win,
                          'time':time,  'hand':sum(hand)/len(hand), 
                          'ping': [min(ping), sum(ping)/len(ping), max(ping)],
                          'frags':frags, 'deaths':deaths, 'suics':suics,
                          'wfrags':wfrags, 'excellent':awards_e, 
                          'impressive':awards_i, 'defence':awards_d,
                          'capture':awards_c,  'assist':awards_a,
                          'weapons':csum(weapon_count), 
                          'ctf':csum(ctf_events)}
                          #'items':csum(items)}
            all_players.append(one_player)
    return all_players


def player_stats(cgames, game_number, player_name):
    """Gather the relevant numbers on a per-game, per-player basis."""
    game = cgames[game_number]
    
    if player_name not in game.validp:
    # Check player has actually played game and is tagged as valid
        return 0
    
    time = game.time - game.ptime[player_name]
    ping = game.players[player_name][0]
    hand = game.handicap[player_name]

    if (game.gametype != '4') and (game.gametype != '3'):
        if game.players[player_name][1] == 1:
            win = 1
        else:
            win = 0
    else:
        try:             # We 'try' it to avoid problems with spectators
            if game.ctfscores[int(game.teams[player_name]) - 1] == max(game.ctfscores):
                win = 1
            else:
                win = 0
        except(IndexError):
            win = 0
        
    awards = []
    awards.extend([n[1] for n in
                   sorted(game.awards[player_name].iteritems())])
    wfrags = [n for n in game.killsp['<world>']].count(player_name)
    deaths = game.deathsp[player_name]
    suics  = len([n for n in game.killsp[player_name]])
    frags  = sum( game.weapons[player_name].values() )
    weapons = [n[1] for n in game.killsp[player_name] if n[0] != player_name]
    weapon_count = []   # per weapon frags
       
    wlist = ['SHOTGUN', 'GAUNTLET', 'MACHINEGUN', 'GRENADE', 'GRENADE_SPLASH',
             'ROCKET', 'ROCKET_SPLASH', 'PLASMA', 'PLASMA_SPLASH', 'RAILGUN',
             'LIGHTNING', 'BFG10K', 'BFG10K_SPLASH', 'TELEFRAG', 'NAIL','CHAIN']
    for w in wlist:
        weapon_count.append(game.weapons[player_name][w[0:3]])

    if game.gametype == '4':
        flags_taken = game.ctf[player_name]['0']
        #flags_captd = game.ctf[player_name].count('1')  # equal to cap award
        flags_retrd = game.ctf[player_name]['2']
        flag_fraggd = game.ctf[player_name]['3']
        ctf_events  = (flags_taken, flags_retrd, flag_fraggd)
    else:
        ctf_events = (0, 0, 0)
    
    #armor = game.itemsp[player_name].count('item_armor_combat')
    #mega  = game.itemsp[player_name].count('item_health_mega')
    #quad  = game.itemsp[player_name].count('item_quad')
    #regen = game.itemsp[player_name].count('item_regen')
    #haste = game.itemsp[player_name].count('item_haste')
    #items = [armor, mega, quad, regen, haste]

    key = ['win', 'time', 'handicap', 'ping', 'frags', 'deaths', 'suics',
           'wfrags', 'awards', 'weapon count', 'ctf_events'] #, 'items']

    return [key, win, time, hand, ping, frags, deaths, suics, 
            wfrags, awards, weapon_count, ctf_events] #/map, items]


def addFromCache(cgames, quotes_list, cache):
    '''Add cached data to player statistics'''
    server_old = cache[-3]               # Make a copy of server data in cache
    quotes_list.extend(cache[-4])        # Add previous quotes to current list
    quotes_list = list(set(quotes_list)) # Eliminate duplicates
    del cache[-4:]                       # Get rid of extra bits in cache file
    R_old = cache                        # Make a copy of previous player data

    if len(cgames) == 0:
        R = R_old                   # No new data, just use the cache
        server = server_old         # Ditto for server data
    else:
        # If there are new games in log, add new data to that from the cache
        R = player_stats_total(cgames)   # Process new player data from log
        server_old.frags = server_old.frags + server.frags
        server_old.gtype = server.gtype  # This we don't add, we update it
        server_old.time  = server_old.time + server.time
        old_names = [player['name'] for player in R_old]
        keys = R[0].keys()
        keys.remove('name')
        keys.remove('ping')
        keys.remove('weapons')
        keys.remove('ctf')
        keys.remove('hand')
        for player in R:
            if player['name'] in old_names:
                index = old_names.index(player['name'])
                min_ping = min( R_old[index]['ping'][0], player['ping'][0] )
                max_ping = max( R_old[index]['ping'][2], player['ping'][2] )
                avg_png1 = R_old[index]['ping'][1]
                avg_png2 = player['ping'][1]
                games1   = R_old[index]['games']
                games2 = player['games']
                ave_ping = (avg_png1*games1 + avg_png2*games2)/(games1 + games2)
                R_old[index]['ping'] = [min_ping, ave_ping, max_ping]
                R_old[index]['weapons'] = csum([ R_old[index]['weapons'],
                                                 player['weapons'] ])
                R_old[index]['ctf']  = csum([ R_old[index]['ctf'], 
                                              player['ctf'] ] )
                avg_han1 = R_old[index]['hand']
                avg_han2 = player['hand']
                R_old[index]['hand'] = (avg_han1*games1 +
                                        avg_han2*games2) / (games1+games2)
                for key in keys:
                    R_old[index][key] = csum( [ [R_old[index][key]],
                                                [player[key]] ] )[0]
            else:
                R_old.append(player)
        R = R_old
        server = server_old   
    return R, quotes_list, server


def writeCache(R, newlines, server, quotes_list, log_file):
    '''Write cache file from updated statistics'''
    cache = R
    log_size = os.path.getsize(log_file)
    date_now = datetime.now().strftime("%c")
    cache.append(quotes_list)
    cache.append(server)
    cache.append(('lines read',newlines - 1))
    cache.append(('Log size on ' + date_now, log_size))
    cache_file = str(log_file[:-4]) + '_cache.p'
    cPickle.dump(cache, open(cache_file, 'wb'))


def results_ordered(R, option, maxnumber):
    '''Sort the dictionary-storing list R according to the key specified
    by option. The inexistent keys 'frag_death_ratio' and 'won_percentage'
    are added here for convenience. maxnumber limits the size of the
    output.'''
    if is_number(maxnumber) is False:
        print "\nINVALID MAXNUMBER VALUE IN results_ordered()"
        print "Check MAXPLAYERS option.\n"
        return
    if maxnumber > len(R):
        maxnumber = len(R)
    elif maxnumber <= 0:
        print "\nINVALID MAXNUMBER VALUE IN results_ordered()"
        print "Check MAXPLAYERS option.\n"
        return
    if option == 'frag_death_ratio':
        Rordered = sorted(R, key = lambda dic:
                          float(dic['frags'])/dic['deaths'], reverse=True)
    elif option == 'won_percentage':
        Rordered = sorted(R, key = lambda dic:
                          float(dic['won'])/dic['games'], reverse=True)
    elif option == 'frags_per_hour':
        Rordered = sorted(R, key = lambda dic:
                          float(dic['frags'])/dic['time'], reverse=True)
    elif option == 'name':
        Rordered = sorted(R, key = lambda dic:
                          float(dic['frags'])/dic['deaths'], reverse=False)
    elif option in R[0].keys():
        Rordered = sorted(R, key = lambda dic: dic[option], reverse=True)
    elif option not in R[0].keys():
        print "\nINVALID ORDERING OPTION IN results_ordered()"
        print "Check spelling?\n"
        return
    return Rordered[0:maxnumber]


def set_gametype(server):
    # Stats only tested with game types 0 and 4, but we'll
    # report the correct game type in any case.
    gametypes = {0: 'Death Match', 1: '1 vs 1', 2: 'Single Death Match',
                3: 'Team Death Match', 4: 'Capture the Flag', 5: 'One-Flag CTF',
                6: 'Overload', 7: 'Harvester', 8: 'Elimination', 
                9: 'CTF Elimination', 10: 'Last Man Standing', 
                11: 'Double Elimination', 12: 'Domination'}

    # If user specifies game type, report it regardless of what pyqscore parsed
    if GTYPE_OVERRIDE in '':
        server.gtype = gametypes[server.gtype]
    elif GTYPE_OVERRIDE in ['ctf', 'CTF']:
        server.gtype = 'Capture the Flag'
    elif GTYPE_OVERRIDE in ['dm', 'DM']:
        server.gtype = 'Death Match'
    elif GTYPE_OVERRIDE != '':
        server.gtype = GTYPE_OVERRIDE
    else:
        server.gtype = 'Unknown'
    return server

    
def dumpJsonfile(R):
    dump_file = log_file[:-4] + '_dump.json'
    f = open(dump_file, 'w')
    json.dump(R, f, sort_keys = True)
    f.close()


def apply_ban(R, BAN_LIST):
    ''''Possibly naive implementation of a black list of players.'''
    R_names = [player['name'] for player in R]
    ban_list_index = []

    for name in BAN_LIST:
        if name in R_names:
            ban_list_index.append(R_names.index(name))
    for i in sorted(ban_list_index, reverse = True):
        del(R[i])
    return R


def name_colour(nick):
    '''Parse Quake colour codes to HTML (uses pyqscores' CSS stylesheet).'''
    for n in range(9):
        code = '^' + str(n)
        html_code = '<SPAN class="c' + str(n) + '">'
        if nick.rfind(code) > -1:
            idx = nick.find(code)
            nick = nick[0:idx] + html_code + nick[idx+2:]
        else:
            nick = nick
    return nick


def is_number(s):
    '''Is 's' a number?'''
    try:
        int(s)
        return True
    except ValueError:
        return False


def make_main_table(R):
    '''List storing main data'''
    main_table_data = []
    for player in R:
        main_table_data.append([player['name'], player['games'], player['won'],
                                str(timedelta(seconds=player['time'])),
                                player['hand'], player['ping'][0], 
                                player['ping'][1], player['ping'][2],
                                player['frags'], player['deaths'],
                                player['suics'], player['wfrags'],
                                player['excellent'], player['impressive']])
    return main_table_data


def make_weapons_table(R):
    '''List storing data for weapons table'''
    weapons_table = []
    for i in xrange(len(R)):
        weapons_table.append([R[i]['name']])
        weapons_table[i].extend(R[i]['weapons'][0:3])      # SHOTG, GAUNT, MGUN
        weapons_table[i].append(sum(R[i]['weapons'][3:5])) # GRENADE
        weapons_table[i].append(sum(R[i]['weapons'][5:7])) # ROCKET
        weapons_table[i].append(sum(R[i]['weapons'][7:9])) # PLASMA
        weapons_table[i].extend(R[i]['weapons'][9:11])     # RAIL, LIGHTG
        weapons_table[i].extend(R[i]['weapons'][14:])      # NAILG, CHAING
        weapons_table[i].append(sum(R[i]['weapons'][11:13])) # BFG
        weapons_table[i].extend(R[i]['weapons'][13:14])      # TELEFRAG
        
    for i in xrange(len(weapons_table)):
        for j in xrange(1, len(weapons_table[i])):
            value = (100. * weapons_table[i][j] / R[i]['frags'])
            weapons_table[i][j] = str(round(value, 2))
    return weapons_table


def make_stats_table(R):
    '''Another table with more numbers'''
    stats_table = []
    for i in xrange(len(R)):
        # name        % games won  frags/deaths    frags/hour      frags/game
        # deaths/hour deaths/game  suic+fall/hour  suic+fall/game  efficiency
        stats_table.append([
                R[i]['name'], 100. * R[i]['won'] / R[i]['games'],
                1.* R[i]['frags'] / (1 + R[i]['deaths']),
                3600. * R[i]['frags']  / R[i]['time'],
                1.* R[i]['frags'] / R[i]['games'],
                3600.* R[i]['deaths'] / R[i]['time'],
                1.* R[i]['deaths'] / R[i]['games'],
                3600. * (R[i]['suics'] + R[i]['wfrags']) / R[i]['time'],
                1. * (R[i]['suics'] + R[i]['wfrags']) / R[i]['games'],
                100. * R[i]['frags'] / (1 + R[i]['frags'] + R[i]['deaths'])])

    for i in xrange(len(stats_table)):
        for j in xrange(1, len(stats_table[i])):
            stats_table[i][j] = str(round(stats_table[i][j], 2))
    return stats_table


def make_quotes_table(quotes_list):
    '''Random quotes'''
    quotes_table = []
    if len(quotes_list) > 0:
        for i in xrange(NUMBER_OF_QUOTES):
            a = quotes_list[int(randint(0,len(quotes_list)-1))]
            quotes_table.append([ name_colour(a[0]), a[1] ] )
    return quotes_table


def make_ctf_table(R):
    '''Table with CTF-related numbers'''
    ctf_table = []
    for i in xrange(len(R)):
        ctf_table.append( [ R[i]['name'] ] )
        ctf_table[i].extend( R[i]['ctf'] )
        ctf_table[i].extend([ R[i]['defence'], R[i]['assist'], R[i]['capture'] ])
    return ctf_table


def make_table(L,  style1_even, style1_odd, style2_even, style2_odd):
    '''Generate HTML table from input data stored in list L.
       style1_even and style1_odd is the style class for the even and 
       odd entries of the first column (player names).
       style2_even and style2_odd are the equivalent the other entries.'''
    lines = []
    
    for i in xrange(len(L)):
        if (mod(i,2) == 0):
            str1 = '<TR>\n'
            str1 = str1 + '<TD><DIV class="%s">' %style1_even + str(L[i][0]) +'</SPAN>\n'
            str1 = str1 + '</DIV></TD>'
            str2 = ''
        else:
            str1 = '<TR>\n'
            str1 = str1 + '<TD><DIV class="%s">' %style1_odd + str(L[i][0]) +'</SPAN>\n'
            str1 = str1 + '</DIV></TD>'
            str2 = ''
        for j in xrange(1,len(L[0])):
            if (mod(i,2) == 0):
                str2 =  str2 + '<TD><DIV class="%s">' %style2_even + str(L[i][j]) + '\n'
                str2 = str2 + '</DIV></TD>\n'
            else:
                str2 =  str2 + '<TD><DIV class="%s">' %style2_odd + str(L[i][j]) + '\n'
                str2 = str2 + '</DIV></TD>\n'
        str2 = str2 + '</TR>\n'
        lines.append(str1)
        lines.append(str2)
    lines.append('</TABLE>')
    return lines


def write_table(f, table_header, table_data, style1_even, style1_odd, 
                style2_even, style2_odd, end_div=False):
    '''Write HTML table to file from a 'header' (The first part of the table
       up to the actual data) and the data stored in a list.'''
    f.write(table_header)
    lines = make_table(table_data, style1_even, style1_odd,
                                    style2_even, style2_odd)
    for line in lines:
        f.write(line)
    if end_div is True:
        f.write('</DIV>')


def open_browser(OPEN_BROWSER, html_file):
    try:    # Why do I use a try statement? I don't even remember...
        if OPEN_BROWSER is True:
            webbrowser.open_new(html_file)
    except:
        print '\nSorry, I could not open a browser for you\n'


def move_html_output(html_file, MOVE_HTML_OUTPUT):
    '''Move HTML file to expected directory'''
    if MOVE_HTML_OUTPUT is True:
        script_dir = os.path.dirname(os.path.realpath(__file__))
        html_file_name = os.path.split(html_file)[-1]
        html_file_new = os.path.join(script_dir, 'html_files', html_file_name)
        if os.path.exists(html_file_new):
            os.remove(html_file_new)
        shutil.copy(html_file, html_file_new)
    else:
        html_file_new = html_file
    return html_file_new


# Raw strings needed to write HTML file
html_header = r'''
<!DOCTYPE html PUBLIC "-//W3C//DTD HTML 4.01//EN"
   "http://www.w3.org/TR/html4/strict.dtd">
      
<HTML>
<HEAD>
<META http-equiv="Content-Type" content="text/html; charset=iso-8859-1">
<META http-equiv="Content-Language" content="en">
<META name="description" content="pyqscore OpenArena stats">
<META name="keywords" content="stats">
<META name="author" content="onak">
<META name="robots" content="noindex, nofollow">
<LINK rel="icon" href="favicon.ico" type="image/x-icon">
<LINK rel="stylesheet" href="../pyqscore_style.css" type="text/css">
<TITLE>OpenArena Stats</TITLE>
</HEAD>

<BODY>
<DIV id="marco">


<DIV class="cuadropresentacion">
<DIV class="update">Last updated on %s </DIV>
<DIV class="intro">OpenArena Stats</DIV>


<DIV class="centrartabla">
<TABLE class="tablaserver">

<TR>
<TD><DIV class="server">Server Name:</DIV></TD>
<TD><DIV class="datoserver">%s </DIV></TD>
<TD><DIV class="server">Server Total Time:</DIV></TD>
<TD><DIV class="datoserver">%s </DIV></TD>
</TR>

<TR>
<TD><DIV class="server">Game Type:</DIV></TD>
<TD><DIV class="datoserver">%s </DIV></TD>
<TD><DIV class="server">Total Frags:</DIV></TD>
<TD><DIV class="datoserver">%s </DIV></TD>
</TR>

</TABLE>
</DIV>
</DIV>

<DIV class="cuadro">
<DIV class="titulocuadro"></DIV>
'''

quotes_table_header = r'''

<DIV class="centrartabla">
<TABLE class="tablaserver" >

<TR>
<TH colspan=2><DIV class="tituloup2">Random quotes</DIV></TH>
</TR>
'''

main_table_header = r'''
<TABLE class="tabladatos">
<TR>
<TH><DIV class="tituloup"></DIV></TH>
<TH><DIV class="tituloup">Total</DIV></TH>
<TH><DIV class="tituloup">Games</DIV></TH>
<TH><DIV class="tituloup">Time</DIV></TH>
<TH><DIV class="tituloup">Mean</DIV></TH>
<TH><DIV class="tituloup">Lowest</DIV></TH>
<TH><DIV class="tituloup">Average</DIV></TH>
<TH><DIV class="tituloup">Highest</DIV></TH>
<TH><DIV class="tituloup">Total</DIV></TH>
<TH><DIV class="tituloup">Total</DIV></TH>
<TH><DIV class="tituloup">Total</DIV></TH>
<TH><DIV class="tituloup">Deads</DIV></TH>
<TH><DIV class="tituloup">Excellent</DIV></TH>
<TH><DIV class="tituloup">Impressive</DIV></TH>
</TR>

<TR>
<TH><DIV class="tituloup3"></DIV></TH>
<TH><DIV class="tituloup3">games</DIV></TH>
<TH><DIV class="tituloup3">won</DIV></TH>
<TH><DIV class="tituloup3">played</DIV></TH>
<TH><DIV class="tituloup3">handicap</DIV></TH>
<TH><DIV class="tituloup3">ping</DIV></TH>
<TH><DIV class="tituloup3">ping</DIV></TH>
<TH><DIV class="tituloup3">ping</DIV></TH>
<TH><DIV class="tituloup3">frags</DIV></TH>
<TH><DIV class="tituloup3">deaths</DIV></TH>
<TH><DIV class="tituloup3">suicides</DIV></TH>
<TH><DIV class="tituloup3">falling</DIV></TH>
<TH><DIV class="tituloup3">awards</DIV></TH>
<TH><DIV class="tituloup3">awards</DIV></TH>
</TR>
'''

ctf_table_header = r'''
<DIV class="centrartabla2">
<TABLE class="tabladatos">

<TR>
<TH><DIV class="tituloup"></DIV></TH>
<TH><DIV class="tituloup">Flags</DIV></TH>
<TH><DIV class="tituloup">Flags</DIV></TH>
<TH><DIV class="tituloup">Flagcarrier</DIV></TH>
<TH><DIV class="tituloup">Defence</DIV></TH>
<TH><DIV class="tituloup">Assist</DIV></TH>
<TH><DIV class="tituloup">Capture</DIV></TH>
<TR>

<TR>
<TD><DIV class="tituloup3"></SPAN></DIV></TD>
<TD><DIV class="tituloup3">taken</DIV></TD>
<TD><DIV class="tituloup3">returned</DIV></TD>
<TD><DIV class="tituloup3">frags</DIV></TD>
<TD><DIV class="tituloup3">awards</DIV></TD>
<TD><DIV class="tituloup3">awards</DIV></TD>
<TD><DIV class="tituloup3">awards</DIV></TD>
</TR>
'''

stats_table_header = r'''
<DIV class="centrartabla2">
<TABLE class="tabladatos">

<TR>
<TH><DIV class="tituloup"></DIV></TH>
<TH><DIV class="tituloup">Games</DIV></TH>
<TH><DIV class="tituloup">Frags/</DIV></TH>
<TH><DIV class="tituloup">Frags</DIV></TH>
<TH><DIV class="tituloup">Frags</DIV></TH>
<TH><DIV class="tituloup">Deaths</DIV></TH>
<TH><DIV class="tituloup">Deaths</DIV></TH>
<TH><DIV class="tituloup">Suics+falling</DIV></TH>
<TH><DIV class="tituloup">Suics+falling</DIV></TH>
<TH><DIV class="tituloup">Efficiency</DIV></TH>
</TR>

<TR>
<TH><DIV class="tituloup3"></DIV></TH>
<TH><DIV class="tituloup3">won %</DIV></TH>
<TH><DIV class="tituloup3">deaths</DIV></TH>
<TH><DIV class="tituloup3">per hour</DIV></TH>
<TH><DIV class="tituloup3">per game</DIV></TH>
<TH><DIV class="tituloup3">per hour</DIV></TH>
<TH><DIV class="tituloup3">per game</DIV></TH>
<TH><DIV class="tituloup3">per hour</DIV></TH>
<TH><DIV class="tituloup3">per game</DIV></TH>
<TH><DIV class="tituloup3"></DIV></TH>
</TR>
'''

weapon_table_header = r'''
<DIV class="centrartabla2">
<TABLE class="tabladatos">

<TR>
<TH><DIV class="tituloup4"></DIV></TH>
<TH><DIV class="tituloup4">Shotgun</DIV></TH>
<TH><DIV class="tituloup4">Gauntlet</DIV></TH>
<TH><DIV class="tituloup4">Machinegun</DIV></TH>
<TH><DIV class="tituloup4">Grenade</DIV></TH>
<TH><DIV class="tituloup4">Rocket</DIV></TH>
<TH><DIV class="tituloup4">Plasma</DIV></TH>
<TH><DIV class="tituloup4">Railgun</DIV></TH>
<TH><DIV class="tituloup4">Lightning</DIV></TH>
<TH><DIV class="tituloup4">Nailgun</DIV></TH>
<TH><DIV class="tituloup4">Chaingun</DIV></TH>
<TH><DIV class="tituloup4">BFG</DIV></TH>
<TH><DIV class="tituloup4">Telefrag</DIV></TH>
</TR>

<TR>
<TD><DIV class="dato"></DIV></TD>
<TD><DIV class="dato"> <IMG SRC="../icons/shotgun.png" width="20" height="20" alt=""></DIV></TD>
<TD><DIV class="dato"> <IMG SRC="../icons/gauntlet.png" width="20" height="20" alt=""></DIV></TD>
<TD><DIV class="dato"> <IMG SRC="../icons/machinegun.png" width="20" height="20" alt=""></DIV></TD>
<TD><DIV class="dato"> <IMG SRC="../icons/grenade.png" width="20" height="20" alt=""></DIV></TD>
<TD><DIV class="dato"> <IMG SRC="../icons/rocket.png" width="20" height="20" alt=""></DIV></TD>
<TD><DIV class="dato"> <IMG SRC="../icons/plasma.png" width="20" height="20" alt=""></DIV></TD>
<TD><DIV class="dato"> <IMG SRC="../icons/railgun.png" width="20" height="20" alt=""></DIV></TD>
<TD><DIV class="dato"> <IMG SRC="../icons/lightning.png" width="20" height="20" alt=""></DIV></TD>
<TD><DIV class="dato"> <IMG SRC="../icons/nailgun.png" width="20" height="20" alt=""></DIV></TD>
<TD><DIV class="dato"> <IMG SRC="../icons/chaingun.png" width="20" height="20" alt=""></DIV></TD>
<TD><DIV class="dato"> <IMG SRC="../icons/bfg.png" width="20" height="20" alt=""></DIV></TD>
<TD><DIV class="dato"> <IMG SRC="../icons/teleporter.png" width="20" height="20" alt=""></DIV></TD>
</TR>
'''

items_table_header = r'''
<TABLE class="tabladatos">

<TR>
<TH><DIV class="tituloup"></Div></TD>
<TH><DIV class="tituloup">Awards</DIV></TD>
'''

def main(log_file=None):
    '''Main wrapper to get the job done'''
    log_file = check_args(log_file)
    cache = check_cache(log_file)
    log, LINE_COUNT = read_log(log_file, cache)
    server, cgames = mainProcessing(log)
    quotes_list = get_quotes(cgames)

    if len(cache) == 0:
        # No cache present, compute player stats
        if len(cgames) != 0:
            R = player_stats_total(cgames)
        else:
            print '\nNo valid games found in log. Play a bit more.\n'
            raise SystemExit()
    else:
        R, quotes_list, server = addFromCache(cgames, quotes_list, cache)

    # write new cache file
    writeCache(R, LINE_COUNT, server, quotes_list, log_file)
    del R[-4:]                  # Once written delete extra bits not needed now
    R = results_ordered(R, SORT_OPTION, MAXPLAYERS)
    server = set_gametype(server)   # update server with correct gametype

    # Dump data in JSON format if so required. Do this now, once data is sorted
    # but before parsing the colour codes: they aren't useful without the .css
    if DUMP_DATA in ('yes', 'Yes', 'YES'):
        dumpJsonfile(R)
    
    R = apply_ban(R, BAN_LIST)
    for player in R:
        player['name'] = name_colour(player['name'])

    # Put together data tables
    main_table_data = make_main_table(R)
    weapons_table = make_weapons_table(R)
    stats_table = make_stats_table(R)
    quotes_table = make_quotes_table(quotes_list)
    ctf_table = make_ctf_table(R)

    html_file = str(log_file)[:-3] + 'html'
    f = open(html_file, 'w')
    f.write(html_header %(datetime.now().strftime("%c"),
                            name_colour(server.hostname),
                            str(timedelta(seconds=server.time)), 
                            server.gtype, server.frags))

    if (NUMBER_OF_QUOTES != 0) and (len(quotes_list) != 0):
        write_table(f, quotes_table_header, quotes_table, 'jugadorquotes',
                    'jugadorquotes', 'datoquotes', 'datoquotes', end_div=True)
        
    write_table(f, main_table_header, main_table_data, 'jugador',
                'jugador2', 'dato', 'dato2', end_div=False)

    if len(R) == 0:
        # This situation may happen when attempting to analyse very small
        # logs with a restrictive ban list.
        print '\nNo player data. Play some more?\n'
        pass
    if DISPLAY_CTF_TABLE is True:
        if any((n['ctf'] != [0, 0, 0]) for n in R):
            write_table(f, ctf_table_header, ctf_table, 'jugador', 
                        'jugador2', 'dato', 'dato2', end_div=True)

    write_table(f, stats_table_header, stats_table, 'jugador', 
                'jugador2', 'dato', 'dato2', end_div=True)
    write_table(f, weapon_table_header, weapons_table, 'jugador2', 
                'jugador', 'dato2', 'dato', end_div=True)
    f.write('</DIV>\n<DIV class="endnote">Powered by pyqscore!</DIV>')
    f.write('</DIV>\n</BODY>\n</HTML>')
    f.close()
    
    html_file_new = move_html_output(html_file, MOVE_HTML_OUTPUT)
    open_browser(OPEN_BROWSER, html_file_new)

if __name__ == '__main__':
    if len(sys.argv) > 1:
        TK_WINDOW = False
    if TK_WINDOW is True:
        options = {'filetypes':[('log files', '*.log')]}
        logfile = tkFileDialog.askopenfilename(**options)
        main(logfile)
    else:
        main()



