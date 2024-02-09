from flask import Blueprint, request, jsonify
from google.cloud import datastore
import json
import constants
from auth import AuthError, verify_jwt
from datetime import datetime, timezone

client = datastore.Client()
bp = Blueprint("playlists", __name__, url_prefix="/playlists")


@bp.app_errorhandler(AuthError)
def handle_auth_error(ex):
    response = jsonify(ex.error)
    response.status_code = ex.status_code
    return response


@bp.route('', methods=['GET', 'POST'])
def response():
    if request.method == 'GET':
        response_error = enforce_json_accept_header()
        if response_error:
            return response_error

        query = client.query(kind=constants.playlists)

        try:
            payload = verify_jwt(request)
            query.add_filter("owner", "=", payload["sub"])
        except AuthError:
            query.add_filter("public", "=", True)

            # Perform a separate query to get the total count
        total_count_query = client.query(kind=constants.playlists)
        try:
            payload = verify_jwt(request)
            total_count_query.add_filter("owner", "=", payload["sub"])
        except AuthError:
            total_count_query.add_filter("public", "=", True)

        total_playlists = len(list(total_count_query.fetch()))

        start_cursor = request.args.get('cursor')
        query_iter = query.fetch(start_cursor=start_cursor, limit=5)
        pages = query_iter.pages
        results = list(next(pages))

        next_cursor = query_iter.next_page_token
        if next_cursor:
            next_url = request.base_url + "?cursor=" + next_cursor.decode()
        else:
            next_url = None

        for playlist in results:
            playlist['id'] = playlist.key.id
            playlist['self'] = request.host_url + "playlists/" + str(playlist.key.id)
        output = {
            'playlists': results,
            'total_playlists': total_playlists
        }
        if next_url:
            output['next'] = next_url
        return jsonify(output), 200
    elif request.method == 'POST':
        response_error = enforce_json_accept_header()
        if response_error:
            return response_error

        content = request.get_json()
        required_fields = ['title', 'public']
        for field in required_fields:
            if field not in content:
                return jsonify({"Error": "The request object is missing at least one of the required attributes"}), 400
        payload = verify_jwt(request)

        new_playlist = datastore.entity.Entity(key=client.key(constants.playlists))
        new_playlist.update({
            'title': content['title'],
            'public': content['public'],
            'date_added': datetime.now(timezone.utc).date().isoformat(),
            'songs': [],
            'owner': payload['sub']
        })
        client.put(new_playlist)
        new_playlist['id'] = new_playlist.key.id
        new_playlist['self'] = request.url + "/" + str(new_playlist.key.id)
        return jsonify(new_playlist), 201


@bp.route('/<playlist_id>', methods=['GET', 'PUT', 'PATCH', 'DELETE'])
def response_id(playlist_id):
    if request.method == 'GET':
        response_error = enforce_json_accept_header()
        if response_error:
            return response_error

        payload = verify_jwt(request)
        playlist_key = client.key(constants.playlists, int(playlist_id))
        playlist = client.get(key=playlist_key)
        if playlist is None:
            return jsonify({"Error": "No playlist with this playlist_id exists"}), 404
        if payload['sub'] != playlist['owner']:
            return jsonify({'Error': 'You are not the owner of this playlist'}), 403

        playlist['id'] = playlist.key.id
        playlist['self'] = request.url
        for song in playlist['songs']:
            song['self'] = request.host_url + "songs/" + str(song['id'])
        return jsonify(playlist), 200
    elif request.method == 'PUT':
        response_error = enforce_json_accept_header()
        if response_error:
            return response_error

        payload = verify_jwt(request)
        playlist_key = client.key(constants.playlists, int(playlist_id))
        playlist = client.get(key=playlist_key)
        if playlist is None:
            return jsonify({"Error": "No playlist with this playlist_id exists"}), 404
        if payload['sub'] != playlist['owner']:
            return jsonify({'Error': 'You are not the owner of this playlist'}), 403

        content = request.get_json()
        if 'id' in content:
            return jsonify({"Error": "The playlist ID cannot be edited"}), 405
        required_fields = ['title', 'public', 'date_added', 'songs', 'owner']
        for field in required_fields:
            if field not in content:
                return jsonify({"Error": "The request object is missing at least one of the required attributes"}), 400

        playlist.update({
            'title': content['title'],
            'public': content['public'],
            'date_added': content['date_added'],
            'songs': content['songs'],
            'owner': content['owner']
        })
        client.put(playlist)
        playlist['id'] = playlist.key.id
        playlist['self'] = request.url
        return jsonify(playlist), 200
    elif request.method == 'PATCH':
        response_error = enforce_json_accept_header()
        if response_error:
            return response_error

        payload = verify_jwt(request)
        playlist_key = client.key(constants.playlists, int(playlist_id))
        playlist = client.get(key=playlist_key)

        if playlist is None:
            return jsonify({"Error": "No playlist with this playlist_id exists"}), 404
        if payload['sub'] != playlist['owner']:
            return jsonify({'Error': 'You are not the owner of this playlist'}), 403

        content = request.get_json()
        if 'id' in content:
            return jsonify({"Error": "The playlist ID cannot be edited"}), 405

        for key in ["title", "public", "date_added", "songs", "owner"]:
            if key in content:
                playlist[key] = content[key]

        client.put(playlist)
        playlist['id'] = playlist.key.id
        playlist['self'] = request.url
        return jsonify(playlist), 200
    elif request.method == 'DELETE':
        payload = verify_jwt(request)
        playlist_key = client.key(constants.playlists, int(playlist_id))
        playlist = client.get(key=playlist_key)

        if playlist is None:
            return jsonify({"Error": "No playlist with this playlist_id exists"}), 404
        if payload['sub'] != playlist['owner']:
            return jsonify({'Error': 'You are not the owner of this playlist'}), 403

        # might have to delete playlist from user
        user_query = client.query(kind=constants.users)
        user_query.add_filter('sub', '=', payload['sub'])
        user_query.add_filter('playlists.id', '=', playlist_id)
        users = list(user_query.fetch())
        print(users)
        if users:
            user = users[0]
            print(user)
            user['playlists'].remove({'id': playlist_id})
            client.put(user)

        client.delete(playlist_key)
        return jsonify(''), 204
    else:
        return jsonify({"Error": "Method not recognized"}), 400


@bp.route('/<playlist_id>/users/<user_id>', methods=['PUT', 'DELETE'])
def assign_playlist_to_user(playlist_id, user_id):
    if request.method == 'PUT':
        response_error = enforce_json_accept_header()
        if response_error:
            return response_error

        payload = verify_jwt(request)
        playlist_key = client.key(constants.playlists, int(playlist_id))
        playlist = client.get(key=playlist_key)
        user_key = client.key(constants.users, int(user_id))
        user = client.get(key=user_key)

        if playlist is None:
            return jsonify({"Error": "No playlist with this playlist_id exists"}), 404
        if user is None:
            return jsonify({"Error": "No user with this user_id exists"}), 404
        if payload['sub'] != playlist['owner']:
            return jsonify({'Error': 'You are not the owner of this playlist'}), 403

        for p in user['playlists']:
            if p['playlist_id'] == playlist_id:
                return jsonify({"Error": "User already added this playlist"}), 400

        user['playlists'].append({'id': playlist_id})
        client.put(user)
        return jsonify(''), 200
    elif request.method == 'DELETE':
        payload = verify_jwt(request)
        playlist_key = client.key(constants.playlists, int(playlist_id))
        playlist = client.get(key=playlist_key)
        user_key = client.key(constants.users, int(user_id))
        user = client.get(key=user_key)

        if playlist is None:
            return jsonify({"Error": "No playlist with this playlist_id exists"}), 404
        if user is None:
            return jsonify({"Error": "No user with this user_id exists"}), 404
        if payload['sub'] != playlist['owner']:
            return jsonify({'Error': 'You are not the owner of this playlist'}), 403

        for p in user['playlists']:
            if p['playlist_id'] == playlist_id:
                user['playlists'].remove({'id': playlist_id})
                client.put(user)
                return jsonify(''), 204
        return jsonify({"Error": "User does not have this playlist"}), 400
    else:
        return jsonify({"Error": "Method not recognized"}), 400


@bp.route('/<playlist_id>/songs/<song_id>', methods=['PUT', 'DELETE'])
def assign_song_to_playlist(playlist_id, song_id):
    if request.method == 'PUT':
        payload = verify_jwt(request)
        playlist_key = client.key(constants.playlists, int(playlist_id))
        playlist = client.get(key=playlist_key)

        if playlist is None:
            return jsonify({"Error": "No playlist with this playlist_id exists"}), 404
        if payload['sub'] != playlist['owner']:
            return jsonify({'Error': 'You are not the owner of this playlist'}), 403

        if not song_exists(song_id):
            return jsonify({"error": "Song does not exist"}), 404

        if any(song['id'] == song_id for song in playlist['songs']):
            return jsonify({"error": "Song is already in the playlist"}), 400

        playlist['songs'].append({'id': song_id})
        client.put(playlist)
        return jsonify(''), 200
    elif request.method == 'DELETE':
        payload = verify_jwt(request)
        playlist_key = client.key(constants.playlists, int(playlist_id))
        playlist = client.get(key=playlist_key)

        if playlist is None:
            return jsonify({"Error": "No playlist with this playlist_id exists"}), 404
        if payload['sub'] != playlist['owner']:
            return jsonify({'Error': 'You are not the owner of this playlist'}), 403

        if not song_exists(song_id):
            return jsonify({"error": "Song does not exist"}), 404

        playlist['songs'].remove({'id': song_id})
        client.put(playlist)
        return jsonify(''), 204
    else:
        return jsonify({"Error": "Method not recognized"}), 400


@bp.route('/<playlist_id>/songs', methods=['GET'])
def get_playlist_songs(playlist_id):
    if request.method() == 'GET':
        payload = verify_jwt(request)
        playlist_key = client.key(constants.playlists, int(playlist_id))
        playlist = client.get(key=playlist_key)

        if playlist is None:
            return jsonify({"Error": "No playlist with this playlist_id exists"}), 404
        if payload['sub'] != playlist['owner']:
            return jsonify({'Error': 'You are not the owner of this playlist'}), 403

        song_list = []
        for song in playlist['songs']:
            song_key = client.key(constants.songs, int(song['id']))
            song = client.get(key=song_key)
            song['id'] = song.key.id
            song['self'] = request.url_root + "songs/" + str(song.key.id)
        output = {
            'songs': song_list
        }
        return jsonify(output), 200
    else:
        return jsonify({"Error": "Method not recognized"}), 400


def enforce_json_accept_header():
    if 'application/json' not in request.accept_mimetypes:
        return jsonify({"Error": "Request must include 'Accept: application/json' header"}), 406


def song_exists(song_id):
    song_key = client.key(constants.songs, int(song_id))
    song = client.get(key=song_key)
    return song is not None
