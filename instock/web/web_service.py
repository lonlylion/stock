#!/usr/local/bin/python3
# -*- coding: utf-8 -*-


import os.path
import sys
from abc import ABC

import tornado.httpserver
import tornado.ioloop
import tornado.options
from tornado import gen

# 在项目运行时，临时将项目路径添加到环境变量
cpath_current = os.path.dirname(os.path.dirname(__file__))
cpath = os.path.abspath(os.path.join(cpath_current, os.pardir))
sys.path.append(cpath)

from instock.lib.simple_logger import get_logger

# 获取logger，指定日志文件
logger = get_logger(__name__, log_file="stock_web.log", log_dir="log")
from instock.lib.database_factory import get_database, db_config, DatabaseType
import instock.lib.version as version
import instock.web.dataTableHandler as dataTableHandler
import instock.web.dataIndicatorsHandler as dataIndicatorsHandler
import instock.web.dataDownloadHandler as dataDownloadHandler
import instock.web.dataUpdateHandler as dataUpdateHandler
import instock.web.jobUpdateHandler as jobUpdateHandler
import instock.web.base as webBase
import instock.web.configHandler as configHandler

__author__ = 'myh '
__date__ = '2023/3/10 '


class Application(tornado.web.Application):
    def __init__(self):
        handlers = [
            # 设置路由
            (r"/", HomeHandler),
            (r"/instock/", HomeHandler),
            # 使用datatable 展示报表数据模块。
            (r"/instock/api_data", dataTableHandler.GetStockDataHandler),
            (r"/instock/data", dataTableHandler.GetStockHtmlHandler),
            # 独立搜索页面
            (r"/instock/search", SearchPageHandler),
            # 获得股票指标数据。
            (r"/instock/data/indicators", dataIndicatorsHandler.GetDataIndicatorsHandler),
            # 加入关注
            (r"/instock/control/attention", dataIndicatorsHandler.SaveCollectHandler),
            # 数据下载页面
            (r"/instock/data_download", dataDownloadHandler.DataDownloadPageHandler),
            # 数据下载API
            (r"/instock/data_download_api", dataDownloadHandler.DataDownloadApiHandler),
            # 文件下载
            (r"/instock/download/(.*)", dataDownloadHandler.FileDownloadHandler),
            # 数据更新API
            (r"/instock/data_update", dataUpdateHandler.DataUpdateHandler),
            # 数据更新状态查询
            (r"/instock/data_update_status", dataUpdateHandler.DataUpdateStatusHandler),
            # 数据检查
            (r"/instock/data_check", dataUpdateHandler.DataCheckHandler),
            # 细粒度job更新API
            (r"/instock/job_update", jobUpdateHandler.JobUpdateHandler),
            # job更新状态查询
            (r"/instock/job_update_status", jobUpdateHandler.JobUpdateStatusHandler),
            # job列表查询
            (r"/instock/job_list", jobUpdateHandler.JobListHandler),
            # 菜单到job映射
            (r"/instock/menu_to_job", jobUpdateHandler.MenuToJobMappingHandler),
            # AI综合分析页面
            (r"/instock/ai_analysis", AIPageHandler),
            # 代理配置页面
            (r"/instock/proxy_config", ProxyConfigPageHandler),
            # 定时任务管理页面
            (r"/instock/schedule_config", ScheduleConfigPageHandler),
            # 配置管理API
            (r"/instock/api/get_config", configHandler.GetConfigHandler),
            (r"/instock/api/save_config", configHandler.SaveConfigHandler),
            (r"/instock/api/test_ai", configHandler.AiTestHandler),
        ]
        settings = dict(  # 配置
            template_path=os.path.join(os.path.dirname(__file__), "templates"),
            static_path=os.path.join(os.path.dirname(__file__), "static"),
            xsrf_cookies=False,  # True,
            # cookie加密
            cookie_secret="027bb1b670eddf0392cdda8709268a17b58b7",
            debug=True,
        )
        super(Application, self).__init__(handlers, **settings)
        # 根据数据库类型初始化连接
        if db_config.db_type == DatabaseType.MYSQL:
            try:
                import instock.lib.torndb as torndb
                import instock.lib.database as mdb
                self.db = torndb.Connection(**mdb.MYSQL_CONN_TORNDB)
                logger.info("MySQL连接初始化成功")
            except Exception as e:
                logger.error(f"MySQL连接初始化失败: {e}")
                self.db = None
        else:
            # ClickHouse模式，不需要torndb连接
            self.db = None
            logger.info("使用ClickHouse模式，跳过MySQL连接初始化")


# 首页handler。
class HomeHandler(webBase.BaseHandler, ABC):
    @gen.coroutine
    def get(self):
        self.render("index.html",
                    stockVersion=version.__version__,
                    leftMenu=webBase.GetLeftMenu(self.request.uri))


# 搜索页面handler。
class SearchPageHandler(webBase.BaseHandler, ABC):
    @gen.coroutine
    def get(self):
        import instock.lib.trade_time as trd
        run_date, run_date_nph = trd.get_trade_date_last()
        date_now_str = run_date.strftime("%Y-%m-%d")
        
        self.render("stock_search.html",
                    date_now=date_now_str,
                    leftMenu=webBase.GetLeftMenu(self.request.uri))


# AI综合分析页面handler
class AIPageHandler(webBase.BaseHandler, ABC):
    @gen.coroutine
    def get(self):
        import instock.lib.trade_time as trd
        run_date, run_date_nph = trd.get_trade_date_last()
        date_now_str = run_date.strftime("%Y-%m-%d")
        
        self.render("ai_analysis.html",
                    date_now=date_now_str,
                    leftMenu=webBase.GetLeftMenu(self.request.uri))


# 代理配置页面handler
class ProxyConfigPageHandler(webBase.BaseHandler, ABC):
    @gen.coroutine
    def get(self):
        import instock.lib.trade_time as trd
        run_date, run_date_nph = trd.get_trade_date_last()
        date_now_str = run_date.strftime("%Y-%m-%d")
        
        self.render("proxy_config.html",
                    date_now=date_now_str,
                    leftMenu=webBase.GetLeftMenu(self.request.uri))


class ScheduleConfigPageHandler(webBase.BaseHandler, ABC):
    @gen.coroutine
    def get(self):
        import instock.lib.trade_time as trd
        run_date, run_date_nph = trd.get_trade_date_last()
        date_now_str = run_date.strftime("%Y-%m-%d")

        self.render("schedule_config.html",
                    date_now=date_now_str,
                    leftMenu=webBase.GetLeftMenu(self.request.uri))


def main():
    # tornado.options.parse_command_line()
    tornado.options.options.logging = None

    http_server = tornado.httpserver.HTTPServer(Application())
    port = 9988
    http_server.listen(port)
    logger.info(f"服务已启动，web地址 : http://localhost:{port}/")

    tornado.ioloop.IOLoop.current().start()


if __name__ == "__main__":
    main()
