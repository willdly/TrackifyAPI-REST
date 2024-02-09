from flask import Blueprint, request, jsonify
from google.cloud import datastore
import json
import constants
from auth import AuthError, verify_jwt

client = datastore.Client()
bp = Blueprint("songs", __name__, url_prefix="/songs")


@bp.route('', methods=['GET', 'POST'])
def response():
    if request.method == 'GET':
        response_error = enforce_json_accept_header()
        if response_error:
            return response_error

        query = client.query(kind=constants.songs)
        start_cursor = request.args.get('cursor')
        query_iter = query.fetch(start_cursor=start_cursor, limit=5)
        pages = query_iter.pages
        results = list(next(pages))
        next_cursor = query_iter.next_page_token
        if next_cursor:
            next_url = request.base_url + "?cursor=" + next_cursor.decode()
        else:
            next_url = None
        for song in results:
            song['id'] = song.key.id
            song['self'] = request.host_url + "songs/" + str(song.key.id)
        output = {
            'songs': results,
            'total_songs': len(list(query.fetch()))
        }
        if next_url:
            output['next'] = next_url
        return jsonify(output), 200
    elif request.method == 'POST':
        response_error = enforce_json_accept_header()
        if response_error:
            return response_error

        content = request.get_json()
        required_fields = ['title', 'artists', 'album', 'duration_s',]
        for field in required_fields:
            if field not in content:
                return jsonify({"Error": "The request object is missing at least one of the required attributes"}), 400

        existing_song_query = client.query(kind=constants.songs)
        existing_song_query.add_filter('title', '=', content['title'])
        existing_song_query.add_filter('artists', '=', content['artists'])
        existing_song_query.add_filter('album', '=', content['album'])
        existing_song_query.add_filter('duration_s', '=', content['duration_s'])

        existing_songs = list(existing_song_query.fetch())

        if existing_songs:
            # Song with similar attributes already exists
            return jsonify({"Error": "A similar song already exists"}), 409

        new_song = datastore.entity.Entity(key=client.key(constants.songs))
        new_song.update({
            'title': content['title'],
            'artists': content['artists'],
            'album': content['album'],
            'duration_s': content['duration_s']
        })
        client.put(new_song)
        new_song['id'] = new_song.key.id
        new_song['self'] = request.url + "/" + str(new_song.key.id)
        return jsonify(new_song), 201
    else:
        return jsonify({"Error": "Method not recognized"}), 400


@bp.route('/<song_id>', methods=['GET', 'PUT', 'PATCH', 'DELETE'])
def response_id(song_id):
    if request.method == 'GET':
        response_error = enforce_json_accept_header()
        if response_error:
            return response_error

        song_key = client.key(constants.songs, int(song_id))
        song = client.get(key=song_key)
        if song is None:
            return jsonify({"Error": "Song does not exist"}), 404
        song['id'] = song.key.id
        song['self'] = request.url
        return jsonify(song), 200
    elif request.method == 'PUT':
        response_error = enforce_json_accept_header()
        if response_error:
            return response_error

        content = request.get_json()
        song_key = client.key(constants.songs, int(song_id))
        song = client.get(key=song_key)
        if song is None:
            return jsonify({"Error": "Song does not exist"}), 404

        if 'id' in content:
            return jsonify({"Error": "The song ID cannot be edited"}), 405
        required_fields = ['title', 'artists', 'album', 'duration_s',]
        for field in required_fields:
            if field not in content:
                return jsonify({"Error": "The request object is missing at least one of the required attributes"}), 400

        song.update({
            'title': content['title'],
            'artists': content['artists'],
            'album': content['album'],
            'duration_s': content['duration_s']
        })
        client.put(song)
        song['id'] = song.key.id
        song['self'] = request.url
        return jsonify(song), 200
    elif request.method == 'PATCH':
        response_error = enforce_json_accept_header()
        if response_error:
            return response_error

        content = request.get_json()
        song_key = client.key(constants.songs, int(song_id))
        song = client.get(key=song_key)
        if song is None:
            return jsonify({"Error": "Song does not exist"}), 404

        if 'id' in content:
            return jsonify({"Error": "The song ID cannot be edited"}), 405

        for key in ['title', 'artists', 'album', 'duration_s']:
            if key in content:
                song.update({key: content[key]})
        client.put(song)
        song['id'] = song.key.id
        song['self'] = request.url
        return jsonify(song), 200
    elif request.method == 'DELETE':
        song_key = client.key(constants.songs, int(song_id))
        song = client.get(key=song_key)
        if song is None:
            return jsonify({"Error": "Song does not exist"}), 404

        playlists_with_song_query = client.query(kind=constants.playlists)
        playlists_with_song_query.add_filter('songs.id', '=', song_id)
        playlists_with_song = list(playlists_with_song_query.fetch())

        for playlist in playlists_with_song:
            playlist['songs'].remove({'id': song_id})
            client.put(playlist)

        client.delete(song)
        return jsonify(''), 204
    else:
        return jsonify({"Error": "Method not recognized"}), 400


def enforce_json_accept_header():
    if 'application/json' not in request.accept_mimetypes:
        return jsonify({"Error": "Request must include 'Accept: application/json' header"}), 406

