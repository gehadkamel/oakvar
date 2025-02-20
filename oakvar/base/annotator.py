class BaseAnnotator(object):

    from ..util.util import get_crv_def
    from ..util.util import get_crx_def
    from ..util.util import get_crg_def
    from ..consts import INPUT_LEVEL_KEY
    from ..consts import VARIANT_LEVEL_KEY
    from ..consts import GENE_LEVEL_KEY

    valid_levels = ["variant", "gene"]
    valid_input_formats = [INPUT_LEVEL_KEY, VARIANT_LEVEL_KEY, GENE_LEVEL_KEY]
    id_col_defs = {"variant": get_crv_def()[0], "gene": get_crg_def()[0]}
    default_input_columns = {
        INPUT_LEVEL_KEY: [x["name"] for x in get_crv_def()],
        VARIANT_LEVEL_KEY: [x["name"] for x in get_crx_def()],
        GENE_LEVEL_KEY: [x["name"] for x in get_crg_def()],
    }
    required_conf_keys = ["level", "output_columns"]

    def __init__(self, *inargs, **inkwargs):
        import os
        import sys
        from pathlib import Path
        from ..util.util import get_args
        from ..consts import cannonical_chroms
        from ..module.local import get_module_conf
        from ..module.data_cache import ModuleDataCache
        from ..exceptions import ModuleLoadingError
        from ..exceptions import LoggerError

        fp = sys.modules[self.__module__].__file__
        if not fp:
            raise ModuleLoadingError(self.__module__)
        self.main_fpath = Path(fp).resolve()
        self.primary_input_path = None
        self.secondary_paths = {}
        self.output_dir = None
        self.output_basename = None
        self.plain_output = None
        self.job_conf_path = None
        self.logger = None
        self.error_logger = None
        self.dbconn = None
        self.cursor = None
        self.cmd_arg_parser = None
        self.json_colnames = None
        self.primary_input_reader = None
        self.output_path = None
        self.last_status_update_time = None
        self.output_columns = None
        self.secondary_readers = {}
        self.output_writer = None
        self.log_path = None
        self.unique_excs = []
        self.log_handler = None
        self.module_options = None
        self._define_cmd_parser()
        self.args = get_args(self.cmd_arg_parser, inargs, inkwargs)
        self.parse_cmd_args(inargs, inkwargs)
        self.serveradmindb = self.args.get("serveradmindb")
        if hasattr(self.args, "live") == False:
            live = False
        else:
            live = self.args["live"]
        self.supported_chroms = set(cannonical_chroms)
        if live:
            return
        self.module_name = self.main_fpath.stem
        self.module_type = "annotator"
        self.annotator_name = self.module_name
        self.module_dir = self.main_fpath.parent
        self.annotator_dir = self.main_fpath.parent
        self.data_dir = self.module_dir / "data"
        self._setup_logger()
        self.conf = get_module_conf(
            self.module_name, module_type=self.module_type, module_dir=self.module_dir
        )
        if self.conf is None:
            raise ModuleLoadingError(self.module_name)
        self._verify_conf()
        self._id_col_name = self.conf["output_columns"][0]["name"]
        if self.logger is None:
            raise LoggerError(module_name=self.module_name)
        if "logging_level" in self.conf:
            self.logger.setLevel(self.conf["logging_level"].upper())
        if "title" in self.conf:
            self.annotator_display_name = self.conf["title"]
        else:
            self.annotator_display_name = os.path.basename(self.module_dir).upper()
        if "version" in self.conf:
            self.annotator_version = self.conf["version"]
        else:
            self.annotator_version = ""
        self.cache = ModuleDataCache(self.module_name, module_type=self.module_type)


    def summarize_by_gene(self, __hugo__, __input_data__):
        pass

    def _log_exception(self, e, halt=True):
        import traceback

        if self.logger:
            self.logger.exception(e)
        else:
            tb = traceback.format_exc()
            print(tb)
        if halt:
            return False
        else:
            return True

    def _verify_conf(self):
        from ..consts import VARIANT_LEVEL_KEY
        from ..consts import GENE_LEVEL_KEY

        if self.conf is None:
            from ..exceptions import SetupError

            raise SetupError(self.module_name)
        from ..exceptions import ConfigurationError

        for k in self.required_conf_keys:
            if k not in self.conf:
                err_msg = 'Required key "%s" not found in configuration' % k
                raise ConfigurationError(err_msg)
        if self.conf["level"] in self.valid_levels:
            self.conf["output_columns"] = [
                self.id_col_defs[self.conf["level"]]
            ] + self.conf["output_columns"]
        else:
            err_msg = "%s is not a valid level. Valid levels are %s" % (
                self.conf["level"],
                ", ".join(self.valid_levels),
            )
            raise ConfigurationError(err_msg)
        if "input_format" in self.conf:
            if self.conf["input_format"] not in self.valid_input_formats:
                err_msg = "Invalid input_format %s, select from %s" % (
                    self.conf["input_format"],
                    ", ".join(self.valid_input_formats),
                )
                raise ConfigurationError(err_msg)
        else:
            if self.conf["level"] == "variant":
                self.conf["input_format"] = VARIANT_LEVEL_KEY
            elif self.conf["level"] == "gene":
                self.conf["input_format"] = GENE_LEVEL_KEY
        if "input_columns" in self.conf:
            id_col_name = self.id_col_defs[self.conf["level"]]["name"]
            if id_col_name not in self.conf["input_columns"]:
                self.conf["input_columns"].append(id_col_name)
        else:
            self.conf["input_columns"] = self.default_input_columns[
                self.conf["input_format"]
            ]

    def _define_cmd_parser(self):
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument("input_file", help="Input file to be annotated.")
        parser.add_argument(
            "-s",
            action="append",
            dest="secondary_inputs",
            help="Secondary inputs. " + "Format as <module_name>:<path>",
        )
        parser.add_argument(
            "-n", dest="run_name", help="Name of job. Default is input file name."
        )
        parser.add_argument(
            "-d",
            dest="output_dir",
            help="Output directory. " + "Default is input file directory.",
        )
        parser.add_argument(
            "-c", dest="confpath", help="Path to optional run conf file."
        )
        parser.add_argument(
            "-p",
            "--plainoutput",
            action="store_true",
            dest="plainoutput",
            help="Skip column definition writing",
        )
        parser.add_argument(
            "--confs", dest="confs", default="{}", help="Configuration string"
        )
        parser.add_argument(
            "--quiet",
            action="store_true",
            dest="quiet",
            default=None,
            help="Silent operation",
        )
        parser.add_argument(
            "--logtofile",
            action="store_true",
            help="Path to a log file. If given without a path, the job's run_name.log will be the log path.",
        )
        self.cmd_arg_parser = parser

    # Parse the command line arguments
    def parse_cmd_args(self, inargs, inkwargs):
        import re
        from pathlib import Path
        from ..util.util import get_args
        from ..util.run import get_module_options

        args = get_args(self.cmd_arg_parser, inargs, inkwargs)
        self.primary_input_path = Path(args["input_file"]).absolute()
        if args["secondary_inputs"]:
            for secondary_def in args["secondary_inputs"]:
                sec_name, sec_path = re.split(r"(?<!\\)=", secondary_def)
                self.secondary_paths[sec_name] = str(Path(sec_path).absolute())
        if args["output_dir"]:
            self.output_dir = args["output_dir"]
        else:
            self.output_dir = str(self.primary_input_path.parent)
        self.plain_output = args["plainoutput"]
        if "run_name" in args and args["run_name"] is not None:
            self.output_basename = args["run_name"]
        else:
            self.output_basename = self.primary_input_path.name
            if Path(self.output_basename).suffix in [".crv", ".crg", ".crx"]:
                self.output_basename = self.output_basename[:-4]
        self.module_options = get_module_options(args)
        self.args = args

    def handle_jsondata(self, output_dict):
        import json

        if self.json_colnames is None:
            return
        for colname in self.json_colnames:
            json_data = output_dict.get(colname, None)
            if json_data is not None:
                json_data = json.dumps(json_data)
            output_dict[colname] = json_data
        return output_dict

    def log_progress(self, lnum):
        from time import time
        from ..util.run import update_status
        from ..consts import JOB_STATUS_UPDATE_INTERVAL

        if not self.last_status_update_time or not self.conf:
            return
        cur_time = time()
        if (
            lnum % 10000 == 0
            or cur_time - self.last_status_update_time > JOB_STATUS_UPDATE_INTERVAL
        ):
            status = f"Running {self.conf['title']} ({self.module_name}): line {lnum}"
            update_status(status, logger=self.logger, serveradmindb=self.serveradmindb)
            self.last_status_update_time = cur_time

    def is_star_allele(self, input_data):
        if self.conf is None:
            return
        return self.conf["level"] == "variant" and input_data.get("alt_base", "") == "*"

    def should_skip_chrom(self, input_data):
        if self.conf is None:
            return
        return (
            self.conf["level"] == "variant"
            and not input_data.get("chrom") in self.supported_chroms
        )

    def fill_empty_output(self, output_dict):
        if self.conf is None:
            return
        for output_col in self.conf["output_columns"]:
            col_name = output_col["name"]
            if col_name not in output_dict:
                output_dict[col_name] = ""
        return output_dict

    def make_json_colnames(self):
        if self.output_columns is None:
            return
        self.json_colnames = []
        for col in self.output_columns:
            if "table" in col and col["table"] == True:
                self.json_colnames.append(col["name"])

    # Runs the annotator.
    def run(self):
        if self.conf is None:
            return
        if self.logger is None:
            return
        from time import time, asctime, localtime
        from ..util.run import update_status

        status = f"started {self.conf['title']} ({self.module_name})"
        update_status(status, logger=self.logger, serveradmindb=self.serveradmindb)
        try:
            start_time = time()
            update_status(
                "started: %s" % asctime(localtime(start_time)),
                logger=self.logger,
                serveradmindb=self.serveradmindb,
            )
            self.base_setup()
            self.last_status_update_time = time()
            self.output_columns = self.conf["output_columns"]
            self.make_json_colnames()
            self.process_file()
            self.postprocess()
            self.base_cleanup()
            status = f"started {self.conf['title']} ({self.module_name})"
            update_status(status, logger=self.logger, serveradmindb=self.serveradmindb)
            end_time = time()
            update_status(
                f"{self.module_name}: finished at {asctime(localtime(end_time))}",
                logger=self.logger,
                serveradmindb=self.serveradmindb,
            )
            run_time = end_time - start_time
            update_status(
                f"{self.module_name}: runtime {run_time:0.3f}s",
                logger=self.logger,
                serveradmindb=self.serveradmindb,
            )
        except Exception as e:
            self._log_exception(e)
        if hasattr(self, "log_handler") and self.log_handler:
            self.log_handler.close()

    def process_file(self):
        for lnum, line, input_data, secondary_data in self._get_input():
            try:
                self.log_progress(lnum)
                # * allele and undefined non-canonical chroms are skipped.
                if self.is_star_allele(input_data) or self.should_skip_chrom(
                    input_data
                ):
                    continue
                output_dict = None
                if secondary_data == {}:
                    output_dict = self.annotate(input_data)
                else:
                    output_dict = self.annotate(
                        input_data, secondary_data=secondary_data
                    )
                # This enables summarizing without writing for now.
                if output_dict is None:
                    continue
                # Handles empty table-format column data.
                output_dict = self.handle_jsondata(output_dict)
                # Preserves the first column
                if output_dict:
                    output_dict[self._id_col_name] = input_data[self._id_col_name]
                # Fill absent columns with empty strings
                output_dict = self.fill_empty_output(output_dict)
                # Writes output.
                if self.output_writer:
                    self.output_writer.write_data(output_dict)
            except Exception as e:
                self._log_runtime_exception(
                    lnum,
                    line,
                    input_data,
                    e,
                    fn=self.primary_input_reader.path
                    if self.primary_input_reader
                    else "?",
                )

    def postprocess(self):
        pass

    async def get_gene_summary_data(self, cf):
        hugos = await cf.exec_db(cf.get_filtered_hugo_list)
        output_columns = await cf.exec_db(
            cf.get_stored_output_columns, self.module_name
        )
        cols = [
            self.module_name + "__" + coldef["name"]
            for coldef in output_columns
            if coldef["name"] != "uid"
        ]
        data = {}
        rows = await cf.exec_db(cf.get_variant_data_for_cols, cols)
        rows_by_hugo = {}
        for row in rows:
            hugo = row[-1]
            if hugo not in rows_by_hugo:
                rows_by_hugo[hugo] = []
            rows_by_hugo[hugo].append(row)
        for hugo in hugos:
            rows = rows_by_hugo[hugo]
            input_data = {}
            for i in range(len(cols)):
                input_data[cols[i].split("__")[1]] = [row[i] for row in rows]
            out = self.summarize_by_gene(hugo, input_data)
            data[hugo] = out
        return data

    def _log_runtime_exception(self, lnum, __line__, __input_data__, e, fn=None):
        import traceback

        err_str = traceback.format_exc().rstrip()
        lines = err_str.split("\n")
        last_line = lines[-1]
        err_str_log = "\n".join(lines[:-1]) + "\n" + ":".join(last_line.split(":")[:2])
        if err_str_log not in self.unique_excs:
            self.unique_excs.append(err_str_log)
            if self.logger:
                self.logger.error(err_str_log)
            else:
                print(err_str_log)
        err_logger_s = f"{fn}:{lnum}\t{str(e)}"
        if self.error_logger:
            self.error_logger.error(err_logger_s)
        else:
            print(err_logger_s)

    # Setup function for the base_annotator, different from self.setup()
    # which is intended to be for the derived annotator.
    def base_setup(self):
        self._setup_primary_input()
        self._setup_secondary_inputs()
        self._setup_outputs()
        self.connect_db()
        self.setup()
        if not hasattr(self, "supported_chroms"):
            self.supported_chroms = set(
                ["chr" + str(n) for n in range(1, 23)] + ["chrX", "chrY"]
            )

    def _setup_primary_input(self):
        if self.conf is None:
            from ..exceptions import SetupError

            raise SetupError(module_name=self.module_name)
        from ..exceptions import ConfigurationError
        from ..util.inout import FileReader

        self.primary_input_reader = FileReader(str(self.primary_input_path))
        requested_input_columns = self.conf["input_columns"]
        defined_columns = self.primary_input_reader.get_column_names()
        missing_columns = set(requested_input_columns) - set(defined_columns)
        if missing_columns:
            if len(defined_columns) > 0:
                err_msg = "Columns not defined in input: %s" % ", ".join(
                    missing_columns
                )
                raise ConfigurationError(err_msg)
            else:
                default_columns = self.default_input_columns[self.conf["input_format"]]
                for col_name in requested_input_columns:
                    try:
                        col_index = default_columns.index(col_name)
                    except ValueError:
                        err_msg = "Column %s not defined for %s format input" % (
                            col_name,
                            self.conf["input_format"],
                        )
                        raise ConfigurationError(err_msg)
                    if col_name == "pos":
                        data_type = "int"
                    else:
                        data_type = "string"
                    self.primary_input_reader.override_column(
                        col_index, col_name, data_type=data_type
                    )

    def _setup_secondary_inputs(self):
        from ..exceptions import SetupError

        if self.conf is None:
            raise SetupError(module_name=self.module_name)
        self.secondary_readers = {}
        try:
            num_expected = len(self.conf["secondary_inputs"])
        except KeyError:
            num_expected = 0
        num_provided = len(self.secondary_paths)
        if num_expected > num_provided:
            raise Exception(
                f"Too few secondary inputs. {num_expected} expected, {num_provided} provided"
            )
        elif num_expected < num_provided:
            raise Exception(
                "Too many secondary inputs. %d expected, %d provided"
                % (num_expected, num_provided)
            )
        for sec_name, sec_input_path in self.secondary_paths.items():
            key_col = (
                self.conf["secondary_inputs"][sec_name]
                .get("match_columns", {})
                .get("secondary", "uid")
            )
            use_columns = self.conf["secondary_inputs"][sec_name].get("use_columns", [])
            fetcher = SecondaryInputFetcher(
                sec_input_path, key_col, fetch_cols=use_columns
            )
            self.secondary_readers[sec_name] = fetcher

    def _setup_outputs(self):
        from os import makedirs
        from pathlib import Path
        from ..util.inout import FileWriter
        from ..exceptions import SetupError
        from ..consts import VARIANT_LEVEL_OUTPUT_SUFFIX
        from ..consts import GENE_LEVEL_OUTPUT_SUFFIX

        if self.conf is None or self.output_dir is None or self.output_basename is None:
            raise SetupError(module_name=self.module_name)
        level = self.conf["level"]
        if level == "variant":
            output_suffix = VARIANT_LEVEL_OUTPUT_SUFFIX
        elif level == "gene":
            output_suffix = GENE_LEVEL_OUTPUT_SUFFIX
        elif level == "summary":
            output_suffix = ".sum"
        else:
            output_suffix = ".out"
        if not (Path(self.output_dir).exists):
            makedirs(self.output_dir)
        self.output_path = Path(self.output_dir) / f"{self.output_basename}.{self.module_name}{output_suffix}"
        if self.plain_output:
            self.output_writer = FileWriter(
                self.output_path,
                include_definition=False,
                include_titles=True,
                titles_prefix="",
            )
        else:
            self.output_writer = FileWriter(self.output_path)
            self.output_writer.write_meta_line("name", self.module_name)
            self.output_writer.write_meta_line(
                "displayname", self.annotator_display_name
            )
            self.output_writer.write_meta_line("version", self.annotator_version)
        skip_aggregation = []
        for col_def in self.conf["output_columns"]:
            self.output_writer.add_column(col_def)
            if not (col_def.get("aggregate", True)):
                skip_aggregation.append(col_def["name"])
        if not (self.plain_output):
            self.output_writer.write_definition(self.conf)
            self.output_writer.write_meta_line(
                "no_aggregate", ",".join(skip_aggregation)
            )

    def connect_db(self):
        from pathlib import Path
        import sqlite3

        db_path = Path(self.data_dir) / (self.module_name + ".sqlite")
        if db_path.exists():
            self.dbconn = sqlite3.connect(str(db_path))
            self.cursor = self.dbconn.cursor()

    def close_db_connection(self):
        if self.cursor is not None:
            self.cursor.close()
        if self.dbconn is not None:
            self.dbconn.close()

    # Placeholder, intended to be overridded in derived class
    def setup(self):
        pass

    def base_cleanup(self):
        if self.output_writer:
            self.output_writer.close()
        # self.invalid_file.close()
        if self.dbconn != None:
            self.close_db_connection()
        self.cleanup()

    # Placeholder, intended to be overridden in derived class
    def cleanup(self):
        pass

    def _setup_logger(self):
        from logging import getLogger
        from ..exceptions import SetupError

        if self.output_basename is None or self.output_dir is None:
            raise SetupError(self.module_name)
        self.logger = getLogger("oakvar." + self.module_name)
        self.error_logger = getLogger("err." + self.module_name)

    def _get_input(self):
        from ..util.inout import AllMappingsParser
        from ..consts import all_mappings_col_name
        from ..consts import mapping_parser_name
        from ..exceptions import SetupError

        if self.conf is None or self.primary_input_reader is None:
            raise SetupError(self.module_name)
        for lnum, line, reader_data in self.primary_input_reader.loop_data():
            try:
                input_data = {}
                for col_name in self.conf["input_columns"]:
                    input_data[col_name] = reader_data[col_name]
                if all_mappings_col_name in input_data:
                    input_data[mapping_parser_name] = AllMappingsParser(
                        input_data[all_mappings_col_name]
                    )
                secondary_data = {}
                for module_name, fetcher in self.secondary_readers.items():
                    input_key_col = (
                        self.conf["secondary_inputs"][module_name]
                        .get("match_columns", {})
                        .get("primary", "uid")
                    )
                    input_key_data = input_data[input_key_col]
                    secondary_data[module_name] = fetcher.get(input_key_data)
                yield lnum, line, input_data, secondary_data
            except Exception as e:
                self._log_runtime_exception(
                    lnum, line, reader_data, e, fn=self.primary_input_reader.path
                )
                continue

    def annotate(self, input_data, secondary_data=None):
        return {
            "default__annotation": "no annotate has been defined",
            "input_data": input_data,
            "secondary_data": secondary_data,
        }

    def live_report_substitute(self, d):
        import re
        from ..exceptions import SetupError

        if self.conf is None:
            raise SetupError(self.module_name)
        if "report_substitution" not in self.conf:
            return d
        rs_dic = self.conf["report_substitution"]
        rs_dic_keys = list(rs_dic.keys())
        for colname in d.keys():
            if colname in rs_dic_keys:
                value = d[colname]
                if colname in ["all_mappings", "all_so"]:
                    for target in list(rs_dic[colname].keys()):
                        value = re.sub(
                            "\\b" + target + "\\b", rs_dic[colname][target], value
                        )
                else:
                    if value in rs_dic[colname]:
                        value = rs_dic[colname][value]
                d[colname] = value
        return d


class SecondaryInputFetcher:
    def __init__(self, input_path, key_col, fetch_cols=[]):
        from ..util.inout import FileReader
        from ..exceptions import ConfigurationError

        self.key_col = key_col
        self.input_path = input_path
        self.input_reader = FileReader(self.input_path)
        valid_cols = self.input_reader.get_column_names()
        if key_col not in valid_cols:
            err_msg = "Key column %s not present in secondary input %s" % (
                key_col,
                self.input_path,
            )
            raise ConfigurationError(err_msg)
        if fetch_cols:
            unmatched_cols = list(set(fetch_cols) - set(valid_cols))
            if unmatched_cols:
                err_msg = "Column(s) %s not present in secondary input %s" % (
                    ", ".join(unmatched_cols),
                    self.input_path,
                )
                raise ConfigurationError(err_msg)
            self.fetch_cols = fetch_cols
        else:
            self.fetch_cols = valid_cols
        self.data = {}
        self.load_input()

    def load_input(self):
        for _, _, all_col_data in self.input_reader.loop_data():
            key_data = all_col_data.get(self.key_col)
            if not key_data:
                continue
            if key_data not in self.data:
                self.data[key_data] = []
            fetch_col_data = {}
            for col in self.fetch_cols:
                val = all_col_data.get(col)
                if val:
                    fetch_col_data[col] = val
            if fetch_col_data:
                self.data[key_data].append(fetch_col_data)

    def get(self, key_data):
        if key_data in self.data:
            return self.data[key_data]
        else:
            return None
