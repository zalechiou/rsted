#!/usr/bin/env python
# all the imports

import os, sys
reload(sys)
sys.setdefaultencoding('utf-8')

from flask import Flask, request, render_template, make_response, url_for, redirect

from rsted.html import rst2html as _rst2html
from rsted.pdf import rst2pdf as _rst2pdf

from flaskext.redis import RedisManager
from flaskext.helpers import render_html

import bz2

# handle relative path references by changing to project directory
run_from = os.path.dirname(os.path.abspath(sys.argv[0]))
if run_from != os.path.curdir:
    os.chdir(run_from)

UPLOAD_FOLDER = 'uploads/'
ALLOWED_EXTENSIONS = set(['rst'])

# create our little application :)
app = Flask(__name__)
app.config.from_pyfile(os.environ.get('RSTED_CONF', 'settings.py'))
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
redis = RedisManager(app).get_instance()

REDIS_EXPIRE = app.config.setdefault('REDIS_EXPIRE', 60*60*24*30*6) # Default 6 months
REDIS_PREFIX = app.config.setdefault('REDIS_PREFIX', 'rst_')


def view_is_active(view_name):
    if request.path == url_for(view_name):
        return 'active'
    return ''

@app.context_processor
def ctx_pro():
    return {
        'MEDIA_URL': '/static/',
        'is_active': view_is_active
    }

@app.route("/")
@render_html('index.html')
def index():
    yield 'js_params', {'theme': request.args.get('theme', '')}

    saved_doc_id = request.args.get('n')
    if saved_doc_id:
        rst = redis.get('%s%s' % (REDIS_PREFIX, saved_doc_id))
        if rst:
            yield 'rst', rst
            yield 'document', saved_doc_id

@app.route('/about/')
def about():
    return render_template('about.html')

@app.route('/convert/')
def convert():
    return render_template('convert.html')

@app.route('/srv/rst2html/', methods=['POST', 'GET'])
def rst2html():
    rst = request.form.get('rst', '')
    theme = request.form.get('theme')
    if theme == 'basic':
        theme = None
    html = _rst2html(rst, theme=theme)
    return html

@app.route('/srv/rst2pdf/', methods=['POST'])
def rst2pdf():
    rst = request.form.get('rst', '')
    theme = request.form.get('theme')
    if theme == 'basic':
        theme = None

    pdf = _rst2pdf(rst, theme=theme)
    responce = make_response(pdf)
    responce.headers['Content-Type'] = 'application/pdf'
    responce.headers['Content-Disposition'] = 'attachment; filename="rst.pdf"'
    responce.headers['Content-Transfer-Encoding'] = 'binary'
    return responce

@app.route('/srv/save_rst/', methods=['POST'])
def save_rst():
    rst = request.form.get('rst')
    if not rst:
        return ''

    from hashlib import md5

    md5sum = md5(rst).hexdigest()
    redis_key = '%s%s' % (REDIS_PREFIX, md5sum)

    if redis.setnx(redis_key, rst) and REDIS_EXPIRE:
        redis.expire(redis_key, REDIS_EXPIRE)
    response = make_response(md5sum)
    response.headers['Content-Type'] = 'text/plain'
    return response

@app.route('/srv/del_rst/', methods=['GET'])
def del_rst():
    saved_id = request.args.get('n')
    if saved_id:
        redis_key = '%s%s' % (REDIS_PREFIX, saved_id)
        redis.delete(redis_key)

    response = make_response()
    response.headers['Content-Type'] = 'text/plain'
    return response

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1] in ALLOWED_EXTENSIONS

@app.route('/srv/convert/', methods=['POST'])
def convert_file():
    if request.method == 'POST':
        file = request.files['rstFile']
        rst = ''
        convert_to = request.form.get('convert_to')
        if file and allowed_file(file.filename):
            rst = file.read()
            if convert_to == 'html':
                html = _rst2html(rst, theme="nature");
                html_bz = bz2.compress(html)
                response = make_response(html_bz)
                response.headers["Content-Disposition"] = "attachment; filename=" + file.filename + ".html.bz2"
                return response
            else if convert_to == 'pdf':
                return redirect(url_for('convert', reason='unsupported format'))
    return redirect(url_for('convert'))

if __name__ == '__main__':
    app.run(host=app.config.get('HOST', '0.0.0.0'),
            port=app.config.get('PORT', 5000))
