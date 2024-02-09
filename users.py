from flask import Blueprint, request, jsonify
from google.cloud import datastore
import json
import constants
from auth import AuthError, verify_jwt

client = datastore.Client()
bp = Blueprint("users", __name__, url_prefix="/users")


@bp.route('', methods=['GET'])
def response():
    if request.method == 'GET':
        if request.method == 'GET':
            response_error = enforce_json_accept_header()
            if response_error:
                return response_error

        query = client.query(kind=constants.users)
        results = list(query.fetch())
        for user in results:
            user['id'] = user.key.id
            for playlist in user['playlists']:
                playlist['self'] = request.host_url + "playlists/" + str(playlist['id'])
        output = {
            'users': results,
            'total_users': len(results)
        }
        return jsonify(output), 200


def enforce_json_accept_header():
    if 'application/json' not in request.accept_mimetypes:
        return jsonify({"Error": "Request must include 'Accept: application/json' header"}), 406