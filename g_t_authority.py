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
from flask import Flask, render_template, request, make_response, session, redirect, g


curr_path = os.path.dirname(__file__)
google_props_filename = os.path.join(curr_path, 'google_properties.json')
props = json.loads(open(google_props_filename, 'r').read())

GOOGLE_CLIENT_ID = props['web']['client_id']

app = Flask(__name__, static_folder='static', static_url_path='')
app.config['SECRET_KEY'] = 'FUCKING_SECRET_KEY_FUCKING_FUCKING_FUCKING!!!'
app.config['DATABASE'] = os.path.join(curr_path, 'db/database.db')


@app.route('/')
def main():
    state = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in xrange(32))
    session['state'] = state
    return render_template('main.html', GOOGLE_CLIENT_ID=GOOGLE_CLIENT_ID, STATE=state)


@app.route('/authorise')
def authorise():
    user_hash = request.args.get('hash')
    print user_hash
    return render_template('authorise.html')


@app.route('/error')
def error():
    return render_template('error.html')


@app.route('/harvest', methods=['POST'])
def harvest():
    interested_data = request.data
    data_type = request.args.get('type')

    if session.get('state') != request.args.get('state'):
        return redirect('/error')

    visitor = {}
    if data_type == u'g':
        visitor['email'] = interested_data
    elif data_type == u't':
        visitor['t_id'] = interested_data
    else:
        return make_response(json.dumps({'error': 'bad request data'}), 200)

    user_hash = save_visitor_credentials(visitor)
    json_result = json.dumps({'user_hash': user_hash})
    print json_result
    return make_response(json_result, 200)

#database functions
def connect_db():
    return sqlite3.connect(app.config['DATABASE'])

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = connect_db()
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    with closing(connect_db()) as db:
        with app.open_resource(os.path.join(curr_path, 'schema.sql'), mode='r') as f:
            db.cursor().executescript(f.read())
        db.commit()


def save_visitor_credentials(visitor):
    db = get_db()
    cur = db.cursor()
    salt = visitor.values()
    salt.append(str(datetime.now()))
    result_salt = str(random.choice(string.ascii_uppercase + string.digits)).join(salt)
    v_hash = hashlib.md5(result_salt).hexdigest()
    cur.execute('INSERT INTO entries(email, t_id, visit, hash) VALUES(?,?,?,?)',
                (visitor.get('email'), visitor.get('t_id'), datetime.now(), v_hash))
    cur.close()
    db.commit()
    return v_hash


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'init_db':
        init_db()
    app.run()
