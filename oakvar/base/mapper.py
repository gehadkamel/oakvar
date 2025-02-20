from typing import Optional


class BaseMapper(object):
    def __init__(self, *inargs, **inkwargs):
        from time import time
        from pathlib import Path
        import pkg_resources
        from pathlib import Path
        from ..module.local import get_module_conf

        self.cmd_parser = None
        self.input_path: Optional[Path] = None
        self.input_dir = None
        self.output_dir: Optional[Path] = None
        self.reader = None
        self.output_base_fname = None
        self.crx_path = None
        self.crg_path = None
        self.crx_writer = None
        self.crg_writer = None
        self.input_fname = None
        self.module_options = None
        self.primary_transcript_paths = None
        self.args = None
        self.logger = None
        self.error_logger = None
        self.unique_excs = []
        self.written_primary_transc = None
        self.define_main_cmd_args()
        self.parse_args(inargs, inkwargs)
        if self.args is None:
            return
        self.t = time()
        self.serveradmindb = self.args.get("serveradmindb")
        main_fpath = self.args.get("script_path", __file__)
        self.module_name = Path(main_fpath).stem
        self.module_dir = Path(main_fpath).parent
        self.mapper_dir = self.module_dir
        self.gene_sources = []
        self.gene_info = {}
        self.setup_logger()
        self.conf = get_module_conf(self.module_name, module_type="mapper")
        self.cravat_version = pkg_resources.get_distribution("oakvar").version

    def define_main_cmd_args(self):
        import argparse

        self.cmd_parser = argparse.ArgumentParser()
        self.cmd_parser.add_argument("input_file", help="Input crv file")
        self.cmd_parser.add_argument(
            "-n", dest="run_name", help="Name of job. " + "Default is input file name."
        )
        self.cmd_parser.add_argument(
            "-d",
            dest="output_dir",
            help="Output directory. " + "Default is input file directory.",
        )
        self.cmd_parser.add_argument(
            "--confs", dest="confs", default="{}", help="Configuration string"
        )
        self.cmd_parser.add_argument(
            "--seekpos", dest="seekpos", default=None, help=argparse.SUPPRESS
        )
        self.cmd_parser.add_argument(
            "--chunksize", dest="chunksize", default=None, help=argparse.SUPPRESS
        )
        self.cmd_parser.add_argument(
            "--primary-transcript",
            dest="primary_transcript",
            # nargs="*",
            default=["mane"],
            help='"mane" for MANE transcripts as primary transcripts, or a path to a file of primary transcripts. MANE is default.',
        )

    def parse_args(self, inargs, inkwargs):
        from os import makedirs
        from pathlib import Path
        from ..util.util import get_args
        from ..util.run import get_module_options
        from ..consts import STANDARD_INPUT_FILE_SUFFIX

        args = get_args(self.cmd_parser, inargs, inkwargs)
        self.input_path = args.get("input_file") or None
        if self.input_path:
            p = Path(self.input_path).absolute()
            self.input_dir = p.parent
            self.input_fname = p.name
            if args.get("output_dir"):
                self.output_dir = Path(args.get("output_dir"))
            else:
                self.output_dir = self.input_dir
            if not self.output_dir.exists():
                makedirs(self.output_dir)
        self.output_base_fname = args.get("run_name")
        if not self.output_base_fname and self.input_fname:
            self.output_base_fname = self.input_fname
            p = Path(self.output_base_fname)
            if p.suffix == STANDARD_INPUT_FILE_SUFFIX:
                self.output_base_fname = p.stem
        self.module_options = get_module_options(args)
        self.primary_transcript_paths = [v for v in args["primary_transcript"] if v]
        self.postfix = args.get("postfix") or ""
        self.args = args

    def setup(self):
        raise NotImplementedError("Mapper must have a setup() method.")

    def extra_setup(self):
        pass

    def end(self):
        pass

    def setup_logger(self):
        from logging import getLogger

        self.logger = getLogger("oakvar.mapper")
        if self.input_path:
            self.logger.info("input file: %s" % self.input_path)
        self.error_logger = getLogger("err." + self.module_name)

    def make_input_reader(self):
        from ..util.inout import FileReader

        if (
            self.args is not None
            and self.args["seekpos"] is not None
            and self.args["chunksize"] is not None
        ):
            self.reader = FileReader(
                self.input_path,
                seekpos=int(self.args["seekpos"]),
                chunksize=int(self.args["chunksize"]),
            )
        else:
            self.reader = FileReader(self.input_path)
        return self.reader

    def make_crx_writer(self):
        from ..util.inout import FileWriter
        from ..util.util import get_crx_def
        from ..consts import crx_idx
        from ..consts import VARIANT_LEVEL_MAPPED_FILE_SUFFIX

        if not self.output_dir or self.conf is None or not self.args:
            raise
        crx_def = get_crx_def()
        crx_fname = f"{self.output_base_fname}{VARIANT_LEVEL_MAPPED_FILE_SUFFIX}"
        self.crx_path = self.output_dir / (crx_fname + self.postfix)
        self.crx_writer = FileWriter(self.crx_path)
        self.crx_writer.add_columns(crx_def)
        self.crx_writer.write_definition(self.conf)
        for index_columns in crx_idx:
            self.crx_writer.add_index(index_columns)
        self.crx_writer.write_meta_line("title", self.conf["title"])
        self.crx_writer.write_meta_line("version", self.conf["version"])
        self.crx_writer.write_meta_line("modulename", self.module_name)
        if not self.primary_transcript_paths:
            self.crx_writer.write_meta_line("primary_transcript_paths", "")
        else:
            for path in self.primary_transcript_paths:
                self.crx_writer.write_meta_line("primary_transcript_path", path)

    def make_crg_writer(self):
        from ..util.util import get_crg_def
        from ..util.inout import FileWriter
        from ..consts import GENE_LEVEL_MAPPED_FILE_SUFFIX
        from ..consts import crg_idx

        if not self.output_dir or not self.args:
            raise
        crg_def = get_crg_def()
        crg_fname = f"{self.output_base_fname}{GENE_LEVEL_MAPPED_FILE_SUFFIX}"
        self.crg_path = self.output_dir / (crg_fname + self.postfix)
        self.crg_writer = FileWriter(self.crg_path)
        self.crg_writer.add_columns(crg_def)
        self.crg_writer.write_definition(self.conf)
        for index_columns in crg_idx:
            self.crg_writer.add_index(index_columns)

    def setup_input_output(self):
        self.make_input_reader()
        self.make_crx_writer()
        self.make_crg_writer()

    def map(self, crv_data: dict):
        _ = crv_data

    def process_file(self):
        from time import time
        from ..util.run import update_status

        if not self.reader or not self.crx_writer or not self.args:
            raise
        count = 0
        last_status_update_time = time()
        crx_data = None
        for ln, line, crv_data in self.reader.loop_data():
            try:
                count += 1
                cur_time = time()
                if count % 10000 == 0 or cur_time - last_status_update_time > 3:
                    status = f"Running gene mapper: line {count}"
                    update_status(
                        status, logger=self.logger, serveradmindb=self.serveradmindb
                    )
                    last_status_update_time = cur_time
                if crv_data["alt_base"] == "*":
                    crx_data = crv_data
                    crx_data["all_mappings"] = "{}"
                else:
                    crx_data = self.map(crv_data)
                if not crx_data:
                    continue
                col_name = "pos_end"
                if col_name not in crx_data:
                    crx_data[col_name] = crv_data[col_name]
            except Exception as e:
                self.log_runtime_error(ln, line, e, fn=self.reader.path)
            if crx_data:
                self.crx_writer.write_data(crx_data)
                self.add_crx_to_gene_info(crx_data)

    def add_crx_to_gene_info(self, crx_data):
        from ..util.inout import AllMappingsParser

        tmap_json = crx_data["all_mappings"]
        # Return if no tmap
        if tmap_json == "":
            return
        tmap_parser = AllMappingsParser(tmap_json)
        for hugo in tmap_parser.get_genes():
            self.gene_info[hugo] = True

    def write_crg(self):
        from ..util.util import get_crg_def

        if self.crg_writer is None:
            return
        sorted_hugos = list(self.gene_info.keys())
        sorted_hugos.sort()
        for hugo in sorted_hugos:
            crg_data = {x["name"]: "" for x in get_crg_def()}
            crg_data["hugo"] = hugo
            self.crg_writer.write_data(crg_data)

    def log_runtime_error(self, ln, line, e, fn=None):
        import traceback

        _ = line
        err_str = traceback.format_exc().rstrip()
        if (
            self.logger is not None
            and self.unique_excs is not None
            and err_str not in self.unique_excs
        ):
            self.unique_excs.append(err_str)
            self.logger.error(err_str)
        if self.error_logger is not None:
            self.error_logger.error(f"{fn}:{ln}\t{str(e)}")

    async def get_gene_summary_data(self, cf):
        from ..util.util import get_crx_def
        from json import loads
        from ..gui.consts import result_viewer_num_var_limit_for_gene_summary_key
        from ..gui.consts import DEFAULT_RESULT_VIEWER_NUM_VAR_LIMIT_FOR_GENE_SUMMARY
        from ..system import get_system_conf

        cols = [
            "base__" + coldef["name"]
            for coldef in get_crx_def()
            if not coldef["name"] in ["cchange", "exonno"]
        ]
        cols.extend(["tagsampler__numsample"])
        data = {}
        rows = await cf.exec_db(cf.get_variant_data_for_cols, cols)
        sys_conf = get_system_conf()
        result_viewer_num_var_limit_for_gene_summary = sys_conf.get(
            result_viewer_num_var_limit_for_gene_summary_key,
            DEFAULT_RESULT_VIEWER_NUM_VAR_LIMIT_FOR_GENE_SUMMARY,
        )
        if len(rows) > result_viewer_num_var_limit_for_gene_summary:
            return {}
        rows_by_hugo = {}
        for row in rows:
            all_mappings = loads(row["base__all_mappings"])
            for hugo in all_mappings.keys():
                if hugo not in rows_by_hugo:
                    rows_by_hugo[hugo] = []
                rows_by_hugo[hugo].append(row)
        hugos = await cf.exec_db(cf.get_filtered_hugo_list)
        for hugo in hugos:
            rows = rows_by_hugo[hugo]
            input_data = {}
            for i in range(len(cols)):
                input_data[cols[i]] = [row[i] for row in rows]
            if hasattr(self, "summarize_by_gene"):
                out = self.summarize_by_gene(hugo, input_data)  # type: ignore
                data[hugo] = out
        return data

    def live_report_substitute(self, d):
        import re

        if self.conf is None or "report_substitution" not in self.conf:
            return
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

    def run(self, __pos_no__):
        from time import time, asctime, localtime
        from ..util.run import update_status

        self.setup()
        self.setup_input_output()
        self.extra_setup()
        if (
            self.args is None
            or self.logger is None
            or self.conf is None
            or self.reader is None
            or self.crx_writer is None
        ):
            raise
        start_time = time()
        tstamp = asctime(localtime(start_time))
        self.logger.info(f"started: {tstamp} | {self.args['seekpos']}")
        status = f"started {self.conf['title']} ({self.module_name})"
        update_status(status, logger=self.logger, serveradmindb=self.serveradmindb)
        self.process_file()
        self.write_crg()
        stop_time = time()
        tstamp = asctime(localtime(stop_time))
        self.logger.info(f"finished: {tstamp} | {self.args['seekpos']}")
        runtime = stop_time - start_time
        self.logger.info("runtime: %6.3f" % runtime)
        self.end()
