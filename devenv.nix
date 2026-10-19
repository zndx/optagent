{ pkgs, config, ... }:

{
  # Local environment for this AMP. Cloudera Machine Learning does not
  # read this file. The workbench runs the tasks in .project-metadata.yaml.
  # https://devenv.sh/reference/options/

  packages = with pkgs; [
    curl
    git
    gnumake
    just
    pkg-config
    protobuf
    openssl
  ];

  # Warehouse front. Same kind of postmaster Gaius (:5444) and Signals
  # (:5455) use for impala_fdw. ElectricSQL PGlite cannot load the .so.
  # Thrift and Boost stay out of `packages`. The FDW task pins Nix
  # thrift so the .so does not link the Impala toolchain's 0.16.
  # Varnish lattice: gaius 6091, signals 6092, aegir 6093, atelier 6094.
  # Cached origins: snapshot, summary lineup, Phoenix sessions frame.
  # The browser still talks to :9892. Origin handlers must not call Varnish.
  services.varnish = {
    enable = true;
    listen = "127.0.0.1:6095";
    vcl = ''
      vcl 4.1;

      backend optagent_origin {
        .host = "127.0.0.1";
        .port = "9892";
        .connect_timeout = 2s;
        .first_byte_timeout = 30s;
      }

      sub vcl_recv {
        if (req.url ~ "^/api/optagent/v1/(snapshot_origin|summary_origin|sessions_origin)") {
          return (hash);
        }
        return (pass);
      }

      sub vcl_backend_response {
        if (bereq.url ~ "^/api/optagent/v1/(snapshot_origin|summary_origin|sessions_origin)") {
          # The app stamps a session cookie on every response. Leaving it
          # on the object makes the builtin VCL refuse to store it.
          unset beresp.http.Set-Cookie;
          if (beresp.status >= 400) {
            if (bereq.is_bgfetch) {
              return (abandon);
            }
            set beresp.ttl = 1s;
            set beresp.grace = 0s;
            set beresp.uncacheable = true;
            return (deliver);
          }
          set beresp.ttl = 60s;
          set beresp.grace = 6h;
          set beresp.uncacheable = false;
          return (deliver);
        }
      }
    '';
  };

  services.postgres = {
    enable = true;
    package = pkgs.postgresql_16;
    port = 5599;
    listen_addresses = "127.0.0.1";
    initialDatabases = [{ name = "optagent"; }];
  };

  tasks."impala-fdw:build" = {
    exec = ''
      set -euo pipefail
      export THRIFT_HOME="${pkgs.thrift}"
      export BOOST_HOME="${pkgs.boost.dev}"
      export PG_DEV="${pkgs.postgresql_16.dev}"
      export PG_OUT="${pkgs.postgresql_16}"
      export PG_LIB="${pkgs.postgresql_16.lib}"
      export CC="${pkgs.stdenv.cc}/bin/cc"
      export CXX="${pkgs.stdenv.cc}/bin/c++"
      export MAKE="${pkgs.gnumake}/bin/make"
      export SIG_KRB5_INC="${pkgs.krb5.dev}/include"
      export SIG_KRB5_LIB="${pkgs.krb5.lib}/lib"
      export SIG_SASL_INC="${pkgs.cyrus_sasl.dev}/include"
      export SIG_SASL_LIB="${pkgs.cyrus_sasl.out}/lib"
      export SIG_SSL_LIB="${pkgs.openssl.out}/lib"
      exec ${config.devenv.root}/scripts/warehouse/build_impala_fdw.sh
    '';
  };

  tasks."impala-fdw:install" = {
    exec = ''
      set -euo pipefail
      exec ${config.devenv.root}/scripts/warehouse/install_impala_fdw.sh
    '';
    after = [ "impala-fdw:build" ];
  };

  languages.python = {
    enable = true;
    package = pkgs.python312;
    uv.enable = true;
    uv.sync.enable = true;
    uv.sync.extras = [ "dev" ];
    venv.enable = true;
  };

  # grok-build's rust-toolchain.toml pins 1.94.0. This shell supplies that
  # toolchain. `just grok-build` compiles zndx/oss-grok-build with it.
  # CML does not read this block.
  languages.rust = {
    enable = true;
    channel = "stable";
    version = "1.94.0";
    components = [ "rustc" "cargo" "clippy" "rustfmt" "rust-src" ];
  };

  # Lattice engine. Status on :50851. Does not host a model.
  processes.engine = {
    exec = "python -m optagent.engine";
    env.OPTAGENT_ENGINE_PORT = "50851";
    env.OPTAGENT_UI_PORT = "9892";
    env.OPTAGENT_PRIMARY_UI = "http://tinybox.dev.vista.zndx.org:9892";
    env.OPTAGENT_VARNISH_PORT = "6095";
    env.OPTAGENT_SESSION_DIR = "${config.devenv.root}/.devenv/state";
    ready.exec = "python -m optagent.engine_ready";
    ready.period = 2;
    ready.probe_timeout = 3;
    ready.failure_threshold = 30;
    ready.timeout = 90;
  };

  # One-shot: same script as the CML "Prepare project" job.
  processes.prepare = {
    exec = "python ${config.devenv.root}/1_job-prepare-project/job.py";
    restart.on = "never";
  };

  # Product UI on the lab lattice, next to Signals :9889 and Gaius :9890.
  # CML sets CDSW_APP_PORT and ignores this bind.
  processes.app = {
    exec = "python ${config.devenv.root}/2_app-serve/app.py";
    env.PORT = "9892";
    env.OPTAGENT_BIND = "0.0.0.0";
    env.OPTAGENT_PRIMARY_UI = "http://tinybox.dev.vista.zndx.org:9892";
    env.OPTAGENT_VARNISH_PORT = "6095";
    env.OPTAGENT_SESSION_DIR = "${config.devenv.root}/.devenv/state";
    env.OPTAGENT_GROK_BIN = "${config.devenv.root}/.devenv/state/bin/grok";
    after = [ "devenv:processes:prepare@completed" ];
    ready.http.get = {
      host = "127.0.0.1";
      port = 9892;
      path = "/health";
    };
    ready.period = 1;
    ready.probe_timeout = 2;
    ready.failure_threshold = 15;
    ready.timeout = 30;
  };

  enterShell = ''
    echo "optagent: $(python --version), rustc $(rustc --version) — just corpora, just test, just grok-build, devenv up (http://tinybox.dev.vista.zndx.org:9892)"
  '';

  # devenv 2 runs this task during `devenv test`. The enterTest string
  # below is the same command for the shell-script test runner.
  tasks."devenv:enterTest" = {
    exec = "python -m pytest";
    showOutput = true;
  };

  enterTest = ''
    python -m pytest
  '';
}
