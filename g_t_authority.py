# coding=utf-8
from contextlib import closing
from datetime import datetime
import os
import sqlite3
import string
import random
import json
import sys
import hashlib
import logging
from flask import Flask, render_template, request, make_response, session, redirect, g, url_for
from werkzeug.local import LocalProxy
from twython import Twython, TwythonError

curr_path = os.path.dirname(__file__)

#loggers init
log = logging.getLogger()
log.setLevel('DEBUG')
log.addHandler(logging.StreamHandler(sys.stdout))

#oauth props init
props_filename = os.path.join(curr_path, 'oauth_properties.json')
props = json.loads(open(props_filename, 'r').read())

GOOGLE_CLIENT_ID = props['google']['client_id']

TTR_CONSUMER_KEY = props['twitter']['consumer_key']
TTR_CONSUMER_SECRET = props['twitter']['consumer_secret']
TTR_REQUEST_TOKEN_URL = props['twitter']['request_token_url']
TTR_CALLBACK_URL = props['twitter']['callback_url']

#flask init
app = Flask(__name__, static_folder='static', static_url_path='')
app.config['SECRET_KEY'] = 'FUCKING_SECRET_KEY_FUCKING_FUCKING_FUCKING!!!'
app.config['DATABASE'] = os.path.join(curr_path, 'db/database.db')


@app.route('/')
def main():
    state = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in xrange(32))
    session['state'] = state
    return render_template('main.html', GOOGLE_CLIENT_ID=GOOGLE_CLIENT_ID, STATE=state)


@app.route('/ttr_auth', methods=['POST', 'GET'])
def ttr_auth():
    twitter = Twython(TTR_CONSUMER_KEY, TTR_CONSUMER_SECRET)
    if request.method == "POST" and session['state'] == request.args.get('state'):
        try:
            ttr_auth = twitter.get_authentication_tokens(callback_url=TTR_CALLBACK_URL)
            oauth_token = ttr_auth['oauth_token']
            print oauth_token
            oauth_secret = ttr_auth['oauth_token_secret']
            print oauth_secret
            session['ttr_oauth_token'] = oauth_token
            session['ttr_oauth_secret'] = oauth_secret
            return redirect(ttr_auth['auth_url'])
        except TwythonError as e:
            return redirect(url_for('error'))

    elif request.method == "GET" and request.args.get('oauth_token') == session['ttr_oauth_token']:
        #check for denied
        if request.args.get('denied'):
            return redirect(url_for('main'))

        oauth_verifier = request.args.get('oauth_verifier')
        if oauth_verifier:
            try:
                twitter = Twython(TTR_CONSUMER_KEY, TTR_CONSUMER_SECRET, session['ttr_oauth_token'],
                                  session['ttr_oauth_secret'])
                authorized_credentials = twitter.get_authorized_tokens(oauth_verifier)
                twitter_id = authorized_credentials['user_id']
                v_hash = get_visitor_hash({'t_id': twitter_id})
                del twitter
                return redirect(url_for('authorise', hash=v_hash))

            except TwythonError as e:
                return redirect(url_for('error'))

        return redirect(url_for('authorise'))


@app.route('/google_auth', methods=['POST'])
def google_auth():
    interested_data = request.data

    if session.get('state') != request.args.get('state'):
        return make_response(json.dumps({'error': 'bad request data'}), 200)

    visitor = {}
    visitor['email'] = interested_data

    user_hash = get_visitor_hash(visitor)
    json_result = json.dumps({'user_hash': user_hash})
    print json_result
    return make_response(json_result, 200)


@app.route('/authorise')
def authorise():
    user_hash = request.args.get('hash')
    identity = get_visitor_identity(user_hash)
    return render_template('authorise.html', identity=identity)


@app.route('/error')
def error():
    return render_template('error.html')



####database functions####
def connect_db():
    return sqlite3.connect(app.config['DATABASE'])


def get_db():
    db = getattr(g, 'db', None)
    if db is None:
        db = g.db = connect_db()
    return db


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, 'db', None)
    if db is not None:
        db.close()


def init_db():
    with closing(connect_db()) as db:
        with app.open_resource(os.path.join(curr_path, 'schema.sql'), mode='r') as f:
            db.cursor().executescript(f.read())
        db.commit()


db = LocalProxy(get_db)


def get_visitor_hash(visitor):
    #db = get_db()
    cur = db.cursor()

    identity = visitor.get('email') or visitor.get('t_id')
    cur.execute("SELECT e_hash FROM entries WHERE e_identity = '%s'" % identity)
    for row in cur:
        cur.close()
        return row[0]

    salt = visitor.values()
    salt.append(str(datetime.now()))
    result_salt = str(random.choice(string.ascii_uppercase + string.digits)).join(salt)
    v_hash = hashlib.md5(result_salt).hexdigest()
    try:
        cur.execute('INSERT INTO entries(email, twitter_id, visit_time, e_hash, e_identity) VALUES(?,?,?,?,?)',
                    (visitor.get('email'), visitor.get('t_id'), datetime.now(), v_hash, identity))
        cur.close()
        db.commit()
    except:
        cur.close()

    return v_hash


def get_visitor_identity(v_hash):
    cur = db.cursor()
    cur.execute("SELECT e_identity FROM entries WHERE e_hash = '%s'" % v_hash)
    for row in cur:
        cur.close()
        return row[0]

    cur.close()
    return None


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'init_db':
        init_db()
    app.run()
