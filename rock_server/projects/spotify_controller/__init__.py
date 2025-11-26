import requests
import json
import os
from flask import Blueprint
from rock_server.utils import current_app
import datetime as dt
from werkzeug.exceptions import Unauthorized, HTTPException


bp = Blueprint("spotify_controller", __name__)
log = current_app.logger

# This code is a little old, and could be cleaned up a little, but it works

TOKEN_FILE = os.path.expanduser("~/.spotify_tokens")
CLIENT_ID = "4f0aa311e38445b5bbb679197709eee1"
CLIENT_SECRET = "8cb46e13ce4a4d35921e1bf0ca2db66b"
# 2025 dump -- needs to be updated every year
# This can be updated by going to the spotify web player, going to the playlist, and copying the playlist ID from the end of the URL
PLAYLISTS = {
    "2025 Dump": "1ozbdD746Xotifh0Jy3D9N",
    "No Words": "3o4eNBILJD005pPNLAnmOv",
    "Off Meds Music": "2VUxCZVmiwA8hktCocQ1hC",
}
API_BASE = 'https://api.spotify.com/v1/'


def dump_playlist_id():
    try:
        return PLAYLISTS[str(dt.datetime.now().year) + " Dump"]
    except Exception as e:
        log.error("Error getting dump playlist ID: " + str(e))
        raise HTTPException("Invalid dump playlist year", 400)

def load_tokens():
    """Load access and refresh tokens from the token file."""
    global AUTH_HEADERS
    if not os.path.exists(TOKEN_FILE):
        raise FileNotFoundError(f"Token file not found at {TOKEN_FILE}. Please create it with access and refresh tokens.")

    with open(TOKEN_FILE, "r") as file:
        tokens = json.load(file)
        return tokens.get("access_token"), tokens.get("refresh_token")

AUTH_HEADERS = {'Authorization': f'Bearer {load_tokens()[0]}'}

def save_tokens(access_token, refresh_token):
    """Save access and refresh tokens to the token file."""
    with open(TOKEN_FILE, "w") as file:
        json.dump({"access_token": access_token, "refresh_token": refresh_token}, file)

def refresh_token():
    """Refresh the Spotify access token."""
    log.info("Refreshing access token...")
    _, token = load_tokens()
    url = "https://accounts.spotify.com/api/token"
    payload = {
        'grant_type': 'refresh_token',
        'refresh_token': token,
    }
    auth = (CLIENT_ID, CLIENT_SECRET)
    response = requests.post(url, data=payload, auth=auth)
    if response.status_code == 200:
        new_access_token = response.json().get('access_token')
        save_tokens(new_access_token, token)  # Save the new access token
        global AUTH_HEADERS
        AUTH_HEADERS = {'Authorization': f'Bearer {new_access_token}'}
        log.debug("Access token refreshed successfully.")
    else:
        log.error(f"Failed to refresh token: {response.status_code} - {response.text}")
        raise Unauthorized("Unable to refresh access token.")

def make_request(endpoint, method='GET', data=None, raw=False, **query_params):
    log.debug(f'Making {method} request to {endpoint}')

    url = API_BASE + endpoint
    if method == 'GET':
        response = requests.get(url, headers=AUTH_HEADERS, params=query_params)
    elif method == 'DELETE':
        response = requests.delete(url, headers=AUTH_HEADERS, params=query_params, json=data)
    elif method == 'POST':
        response = requests.post(url, headers=AUTH_HEADERS, params=query_params, json=data)
    elif method == 'PUT':
        response = requests.put(url, headers=AUTH_HEADERS, params=query_params, json=data)
    else:
        raise TypeError('Invalid method given to make_request')

    if response.status_code == 401:
        log.debug("Access token expired. Attempting to refresh...")
        refresh_token()
        # Retry the request with the refreshed token
        return make_request(endpoint, method, data, **query_params)

    if response.status_code in (200, 201, 204):
        if raw:
            return response
        return response.json() if response.content else None
    else:
        log.error(f'Request to \n{endpoint} Failed with code {response.status_code}')
        return None

def get_current_playing_track():
    response = make_request('me/player/currently-playing')
    if response and response.get('item'):
        return response['item']
    return None

def check_if_track_is_liked(track_id):
    response = make_request('me/tracks/contains', ids=track_id)
    if response is not None and len(response) > 0:
        return response[0]
    return False

def remove_track_from_liked(track_id):
    make_request('me/tracks', method='DELETE', data={"ids": [track_id]})

def add_track_to_playlist(track_id, playlist_id):
    make_request(f'playlists/{playlist_id}/tracks', method='POST', data={"uris": [f"spotify:track:{track_id}"]})

def like_track(track_id):
    """Add a track to the user's liked songs."""
    make_request('me/tracks', method='PUT', data={"ids": [track_id]})

def remove_track_from_playlist(track_id, playlist_id):
    """Remove a track from the specified playlist."""
    make_request(f'playlists/{playlist_id}/tracks', method='DELETE', data={"tracks": [{"uri": f"spotify:track:{track_id}"}]})

def next_song():
    make_request('me/player/next', method='POST', raw=True)

@bp.put("/like")
def like():
    DUMP_PLAYLIST_ID = dump_playlist_id()
    if not DUMP_PLAYLIST_ID:
        log.error("Playlist year doesn't match current year, not liking track.")
        return "Invalid Year", 400

    # Get the current playing track
    current_track = get_current_playing_track()
    if not current_track:
        log.info("No track is currently playing.")
        return "No track is currently playing.", 202

    track_id = current_track['id']
    track_name = current_track['name']
    log.debug(f"Currently playing track: {track_name}")

    # Add the track to Liked Songs
    like_track(track_id)
    log.info(f"Added {track_name} to Liked Songs.")

    remove_track_from_playlist(track_id, DUMP_PLAYLIST_ID)
    log.info(f"Removed {track_name} from playlist {DUMP_PLAYLIST_ID}.")

    return "Success", 204

@bp.put("/unlike")
def unlike():
    # If this errors out, we want it to do it here, not after we've already done things
    DUMP_PLAYLIST_ID = dump_playlist_id()

    # Get the current playing track
    current_track = get_current_playing_track()
    if not current_track:
        log.info("No track is currently playing.")
        return "No track is currently playing.", 202

    track_id = current_track['id']
    track_name = current_track['name']
    log.debug(f"Currently playing track: {track_name}")

    # Check if the track is liked
    if check_if_track_is_liked(track_id):
        log.debug(f"{track_name} is in your Liked Songs.")

        # Remove from Liked Songs
        remove_track_from_liked(track_id)
        log.info(f"Removed {track_name} from your Liked Songs.")

        # Add to specified playlist
        add_track_to_playlist(track_id, DUMP_PLAYLIST_ID)
        log.info(f"Added {track_name} to dump playlist {DUMP_PLAYLIST_ID}.")

        next_song()
    else:
        log.info(f"{track_name} is not in your Liked Songs, nothing to move.")

    return "Success", 204

@bp.put("/add-to-playlist/<playlist>")
def add_to_playlist(playlist):
    if playlist not in PLAYLISTS:
        log.error(f"Invalid playlist: {playlist}")
        return "Invalid Playlist. Options are " + ", ".join(PLAYLISTS.keys()), 400

    # Get the current playing track
    current_track = get_current_playing_track()
    if not current_track:
        log.info("No track is currently playing.")
        return "No track is currently playing.", 202

    track_id = current_track['id']
    track_name = current_track['name']
    # log.info(f"Currently playing track: {track_name}")

    # Add the track to the specified playlist
    add_track_to_playlist(track_id, PLAYLISTS[playlist])
    log.info(f"Added {track_name} to playlist {PLAYLISTS[playlist]}.")

    return "Success", 204
