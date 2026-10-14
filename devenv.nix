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
  ];

  # Warehouse front. Same kind of postmaster Gaius (:5444) and Signals
  # (:5455) use for impala_fdw. ElectricSQL PGlite cannot load the .so.
  # Thrift and Boost stay out of `packages`. The FDW task pins Nix
  # thrift so the .so does not link the Impala toolchain's 0.16.
  services.postgres = {
    enable = true;
    package = pkgs.postgresql_16;
    port = 5466;
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

  # One-shot: same script as the CML "Prepare project" job.
  processes.prepare = {
    exec = "python ${config.devenv.root}/1_job-prepare-project/job.py";
    restart.on = "never";
  };

  # Same script as the CML application. 8123 stays clear of the usual
  # 8080 listeners on a shared workstation. CML uses CDSW_APP_PORT.
  processes.app = {
    exec = "python ${config.devenv.root}/2_app-serve/app.py";
    env.PORT = "8123";
    after = [ "devenv:processes:prepare@completed" ];
    ready.http.get = {
      host = "127.0.0.1";
      port = 8123;
      path = "/health";
    };
    ready.period = 1;
    ready.probe_timeout = 2;
    ready.failure_threshold = 15;
    ready.timeout = 30;
  };

  enterShell = ''
    echo "optagent: $(python --version) — just test, devenv up (http://127.0.0.1:8123)"
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
