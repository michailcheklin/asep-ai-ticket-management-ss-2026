
from flask import Flask, request, redirect, make_response, render_template_string


# fake_idp.py — fake Shibboleth login page for local development

app = Flask(__name__, static_folder="fake_idp_static", static_url_path="/resources")

COOKIE_NAME = "fake_shib_email"

LOGIN_HTML = """<!doctype html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>UDE.Shibboleth | Login</title>
  <link rel="stylesheet"
        href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css">
  <link rel="stylesheet"
        href="https://cdn.jsdelivr.net/npm/@fortawesome/fontawesome-free@6.5.2/css/all.min.css">
  <style>
    body { margin: 0; font-family: Arial, Helvetica, sans-serif; }
    .bg-image--cover {
      background-size: cover;
      background-position: center;
      min-height: 100vh;
    }
    .vh-100 { min-height: 100vh; }
    .dev-banner {
      position: fixed; top: 0; left: 0; right: 0; z-index: 9999;
      background: #fff3cd; border-bottom: 1px solid #ffc107;
      color: #856404; font-size: 12px; text-align: center; padding: 5px;
    }
    .col-white-panel {
      background: white;
      padding-top: 3rem;
      padding-bottom: 1rem;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      min-height: 100vh;
    }
    .input-group-merge .input-group-text {
      background: white;
      border-left: none;
      color: #aaa;
    }
    .input-group-merge input {
      border-right: none;
    }
    .input-group-merge input:focus {
      box-shadow: none;
      border-color: #ced4da;
    }
    .btn-primary {
      background-color: #003366;
      border-color: #003366;
    }
    .btn-primary:hover {
      background-color: #004488;
      border-color: #004488;
    }
    .text-black-50 { color: rgba(0,0,0,.5) !important; }
  </style>
</head>
<body>

<div class="dev-banner">
  &#9888; Fake IdP — development only &nbsp;|&nbsp; any credentials accepted
</div>

<div class="bg-image--cover"
     style="background-image: url('/resources/images/background.jpg'); padding-top: 28px;">
  <div class="row mx-0 vh-100">

    <div class="col col-sm-9 col-md-7 col-lg-6 col-xl-5 col-xxl-4 col-white-panel px-4 px-sm-5">

      <div>
        <!-- logos row -->
        <div class="row d-flex justify-content-between mb-4">
          <div class="col-auto">
            <img src="/resources/images/logo/signet.png" alt="UDE" height="64"
                 onerror="this.style.display='none'">
          </div>
          <div class="col-auto d-flex align-items-center">
            <span class="text-muted small">DFN SAML2 Test SP</span>
          </div>
        </div>

        <!-- heading -->
        <div class="fs-4 mb-1">Shibboleth-Login</div>
        <div class="text-black-50 mb-4">
          DFN SAML2 Test SP
          <div class="small mt-1">DFN Test SP2 (Test Federation), SAML2-only</div>
        </div>

        <!-- form -->
        <form method="POST" action="/login">
          <input type="hidden" name="next" value="{{ next }}">

          <div class="mb-3">
            <label for="username" class="form-label">Username</label>
            <div class="input-group input-group-merge">
              <input id="username" name="username" type="text"
                     class="form-control" placeholder="Username"
                     autocomplete="username" autofocus required>
              <span class="input-group-text">
                <i class="fal fa-fw fa-user"></i>
              </span>
            </div>
          </div>

          <div class="mb-3">
            <a href="https://www.uni-due.de/passwort-reset-info/"
               class="text-muted float-end" target="_blank">
              <small>Forgot your password?</small>
            </a>
            <label for="password" class="form-label">Password</label>
            <div class="input-group input-group-merge">
              <input id="password" name="password" type="password"
                     class="form-control" placeholder="Password"
                     autocomplete="current-password" required>
              <span class="input-group-text">
                <i class="fal fa-fw fa-lock"></i>
              </span>
            </div>
          </div>

          <div class="mb-4">
            <label class="form-label">Optionen</label>
            <div class="form-check form-switch">
              <input type="checkbox" class="form-check-input" id="donotcache">
              <label class="form-check-label" for="donotcache">Don't Remember Login</label>
            </div>
            <div class="form-check form-switch">
              <input type="checkbox" class="form-check-input" id="revokeConsent">
              <label class="form-check-label" for="revokeConsent">
                Clear prior granting of permission for release of your information to this service.
              </label>
            </div>
          </div>

          <div class="d-grid mb-0">
            <button type="submit" class="btn btn-primary">
              <i class="fas fa-sign-in-alt me-1"></i> Login
            </button>
          </div>
        </form>

        <div class="text-black-50 mt-4 small">
          Need Help?
          <a href="https://www.uni-due.de/support/" target="_blank"
             class="text-muted ms-1"><b>Help</b></a>
        </div>
      </div>

      <!-- bottom row -->
      <div class="row d-flex align-items-end justify-content-end mt-3">
        <div class="col-auto">
          <img src="/resources/images/logo/powered-by-ZIM.png" alt="powered by ZIM" height="32"
               onerror="this.style.display='none'">
        </div>
      </div>

    </div><!-- /white panel -->
  </div>
</div>

</body>
</html>"""


@app.route("/")
def index():
    """The user gets redirected from localhost:5000 to the correct login page"""
    return redirect("/login?next=http://localhost:8501")

@app.route("/login", methods=["GET", "POST"])
def login():
    """Login logic + creating email cookie"""
    next_url = request.args.get("next") or request.form.get("next") or "http://localhost:8501"

    if request.method == "POST":
        unikennung = (request.form.get("username") or "user").strip().lower()
        email = f"{unikennung}@uni-due.de"
        response = make_response(redirect(next_url))
        response.set_cookie(COOKIE_NAME, email, max_age=3600, httponly=True, samesite="Lax")
        return response

    return render_template_string(LOGIN_HTML, next=next_url)


if __name__ == "__main__":
    print("\nFake UDE Shibboleth IdP running at http://localhost:5000")
    print("Login: http://localhost:5000/login?next=http://localhost:8501\n")
    app.run(host="0.0.0.0", port=5000, debug=False)
