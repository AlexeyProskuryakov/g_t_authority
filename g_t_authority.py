# coding=utf-8
from contextlib import closing
from datetime import datetime, timedelta
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

days_rot = timedelta(days=30)
time_format = '%Y-%m-%d %H:%M:%S'

#loggers init
log = logging.getLogger(__name__)
log.setLevel('DEBUG')
frmtr = logging.Formatter('%(asctime)s|%(process)d|%(levelname)s|: %(message)s')
try:
    os.mkdir(os.path.join(curr_path, 'logs'))
except:
    pass
fh = logging.FileHandler(os.path.join(curr_path, 'logs', 'result.log'), mode='w+')
fh.setFormatter(frmtr)
sh = logging.StreamHandler(sys.stdout)
sh.setFormatter(frmtr)
log.addHandler(fh)
log.addHandler(sh)

#oauth props init
props_filename = os.path.join(curr_path, 'oauth_properties.json')
props = json.loads(open(props_filename, 'r').read())
GOOGLE_CLIENT_ID = props['google']['client_id']
TTR_CONSUMER_KEY = props['twitter']['consumer_key']
TTR_CONSUMER_SECRET = props['twitter']['consumer_secret']
TTR_CALLBACK_URL = props['twitter']['callback_url']

#flask init
app = Flask(__name__, static_folder='static', static_url_path='')
app.config['SECRET_KEY'] = 'FUCKING_SECRET_KEY_FUCKING_FUCKING_FUCKING!!!'
app.config['DATABASE'] = os.path.join(curr_path, 'db/database.db')

#identities source
t_identities_source_path = os.path.join(curr_path, 't_identities.csv')
g_identities_source_path = os.path.join(curr_path, 'g_identities.csv')


def load_interested_identities(source_google, source_twitter, sep=';'):
    """
    source must be file like object with some separator like
    """
    all_objects = source_google.read()
    objects = [el.strip() for el in all_objects.split(sep) if len(el)]

    extended = source_twitter.read()
    objects.extend([el.strip() for el in extended.split(sep) if len(el)])

    if log.level == logging.DEBUG:
        log.debug('loaded identities:\n')
        for el in objects:
            log.debug(el)

    return objects


def get_interested_identities():
    objects = getattr(g, 'objects', None)
    if objects is None:
        objects = g.objects = load_interested_identities(open(g_identities_source_path, 'r'),
                                                         open(t_identities_source_path, 'r')
        )
    return objects


interested_identities = LocalProxy(get_interested_identities)


@app.route('/')
def main():
    state = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in xrange(32))
    session['state'] = state
    return render_template('main.html', GOOGLE_CLIENT_ID=GOOGLE_CLIENT_ID, STATE=state)


@app.route('/ttr_auth', methods=['POST', 'GET'])
def ttr_auth():
    twitter = Twython(TTR_CONSUMER_KEY, TTR_CONSUMER_SECRET)

    if request.method == "POST" and session['state'] == request.args.get('state'):
        log.info('[][twitter] someone want to login')
        try:
            ttr_auth = twitter.get_authentication_tokens(callback_url=TTR_CALLBACK_URL)
            session['ttr_oauth_token'] = ttr_auth['oauth_token']
            session['ttr_oauth_secret'] = ttr_auth['oauth_token_secret']
            return redirect(ttr_auth['auth_url'])
        except TwythonError as e:
            return redirect(url_for('error'))

    elif request.method == "GET":
        #check for denied
        if request.args.get('denied'):
            return redirect(url_for('main'))

        if request.args.get('oauth_token') == session['ttr_oauth_token']:
            oauth_verifier = request.args.get('oauth_verifier')
            if oauth_verifier:
                try:
                    twitter = Twython(TTR_CONSUMER_KEY, TTR_CONSUMER_SECRET, session['ttr_oauth_token'],
                                      session['ttr_oauth_secret'])
                    authorized_credentials = twitter.get_authorized_tokens(oauth_verifier)
                    twitter_id = authorized_credentials['user_id']
                    v_hash = get_visitor_hash({'t_id': twitter_id})
                    if not v_hash:
                        log.info('[%s][twitter] not allowed' % twitter_id)
                        return redirect(url_for('error'))

                    del twitter
                    log.info('[%s][twitter] authorise' % twitter_id)
                    return redirect(url_for('authorise', hash=v_hash))

                except TwythonError as e:
                    return redirect(url_for('error'))

            return redirect(url_for('authorise'))
    return redirect(url_for('main'))


@app.route('/google_log', methods=['POST'])
def google_log():
    log.info('[][google] someone want to login')
    return make_response('', 200)


@app.route('/google_auth', methods=['POST'])
def google_auth():
    email = request.data

    if session.get('state') != request.args.get('state'):
        return make_response(json.dumps({'error': 'bad request data'}), 200)

    user_hash = get_visitor_hash({'email': email})
    if not user_hash:
        log.info('[%s][google] not allowed' % email)
        return make_response(json.dumps({'error': 'not allowed'}), 200)

    log.info('[%s][google] authorised' % email)
    json_result = json.dumps({'user_hash': user_hash})

    return make_response(json_result, 200)


@app.route('/authorise')
def authorise():
    user_hash = request.args.get('hash')
    identity = get_visitor_identity(user_hash)
    if not identity or not user_hash:
        return redirect(url_for('main'))
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
    cur = db.cursor()
    tstamp = datetime.now()
    identity = visitor.get('email') or visitor.get('t_id')

    if len(interested_identities) and identity not in interested_identities:
        return None

    cur.execute("SELECT e_hash, visit_time FROM entries WHERE e_identity = '%s'" % identity)
    for row in cur:
        e_hash, visit_time = row[0], row[1]
        visit_time = datetime.strptime(visit_time, time_format)

        if tstamp - visit_time > days_rot:
            cur.execute("DELETE FROM entries WHERE e_identity = '%s'" % identity)
            break

        cur.close()
        return e_hash

    salt = visitor.values()
    salt.append(str(datetime.now()))
    result_salt = str(random.choice(string.ascii_uppercase + string.digits)).join(salt)
    v_hash = hashlib.md5(result_salt).hexdigest()
    try:
        cur.execute('INSERT INTO entries(email, twitter_id, visit_time, e_hash, e_identity) VALUES(?,?,?,?,?)',
                    (visitor.get('email'),
                     visitor.get('t_id'),
                     tstamp.strftime(time_format),
                     v_hash,
                     identity))
        cur.close()
        db.commit()
    except:
        cur.close()

    return v_hash


def get_visitor_identity(v_hash):
    cur = db.cursor()
    cur.execute("SELECT e_identity FROM entries WHERE e_hash = '%s' " % v_hash)
    for row in cur:
        cur.close()
        return row[0]

    cur.close()
    return None


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'init_db':
        init_db()
    app.run(host='0.0.0.0', port=5000)
