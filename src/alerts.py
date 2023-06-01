from os import environ
environ["PRODUCTION"] = environ["PRODUCTION"] if "PRODUCTION" in environ and environ["PRODUCTION"] else ""

from signal import signal, SIGINT, SIGTERM
from time import time, mktime
from random import randint
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from aiohttp import TCPConnector, ClientSession
from asyncio import sleep, wait, run, create_task
from orjson import dumps, OPT_SORT_KEYS
from uuid import uuid4
from traceback import format_exc

from discord import Webhook, Embed, File
from discord.errors import NotFound
from discord.utils import MISSING
from google.cloud.firestore import AsyncClient as FirestoreClient
from google.cloud.error_reporting import Client as ErrorReportingClient
from feedparser import parse

from helpers import constants
from Processor import process_chart_arguments, process_task
from DatabaseConnector import DatabaseConnector
from CommandRequest import CommandRequest
from helpers.utils import seconds_until_cycle, get_accepted_timeframes
from helpers.haltmap import HALT_MAP


database = FirestoreClient()
EST = ZoneInfo("America/New_York")

NAMES = {
	"401328409499664394": ("Alpha", "https://storage.alpha.bot/Icon.png"),
	"487714342301859854": ("Alpha (Beta)", MISSING)
}


class AlertsServer(object):
	accountProperties = DatabaseConnector(mode="account")
	guildProperties = DatabaseConnector(mode="guild")
	registeredAccounts = {}


	# -------------------------
	# Startup
	# -------------------------

	def __init__(self):
		self.isServiceAvailable = True
		signal(SIGINT, self.exit_gracefully)
		signal(SIGTERM, self.exit_gracefully)

		self.logging = ErrorReportingClient(service="alerts")

		self.url = "http://candle-server:6900/candle/" if environ['PRODUCTION'] else "http://candle-server:6900/candle/"

		self.haltDataCache = {}
		self.haltMessageCache = {}

	def exit_gracefully(self, signum, frame):
		print("[Startup]: Alerts Server handler is exiting")
		self.isServiceAvailable = False


	# -------------------------
	# Job queue
	# -------------------------

	async def run(self):
		conn = TCPConnector(limit=10)
		async with ClientSession(connector=conn) as session:
			while self.isServiceAvailable:
				try:
					await sleep(seconds_until_cycle())
					t = datetime.now().astimezone(timezone.utc)
					timeframes = get_accepted_timeframes(t)

					if "1m" in timeframes:
						await self.update_accounts()
						await wait([
							create_task(self.process_price_alerts(session)),
							create_task(self.process_halt_alerts(session)),
						])

				except (KeyboardInterrupt, SystemExit): return
				except:
					print(format_exc())
					if environ["PRODUCTION"]: self.logging.report_exception()

	async def update_accounts(self):
		try:
			self.registeredAccounts = await self.accountProperties.keys()
		except (KeyboardInterrupt, SystemExit): pass
		except:
			print(format_exc())
			if environ["PRODUCTION"]: self.logging.report_exception()


	# -------------------------
	# Price Alerts
	# -------------------------

	async def process_price_alerts(self, session):
		startTimestamp = time()
		try:
			requestMap = {}
			alerts = []
			users = database.document("details/marketAlerts").collections()

			async for user in users:
				accountId = user.id
				if not environ["PRODUCTION"] and accountId != "ebOX1w1N2DgMtXVN978fnL0FKCP2": continue

				authorId = accountId if accountId.isdigit() else self.registeredAccounts.get(accountId)
				if authorId is None: continue

				async for alert in user.stream():
					key = dumps(alert.to_dict()["request"]["ticker"], option=OPT_SORT_KEYS)
					if key in requestMap:
						requestMap[key][1].append(len(alerts))
					else:
						requestMap[key] = [
							create_task(self.fetch_candles(session, alert.to_dict())),
							[len(alerts)]
						]
					alerts.append((authorId, accountId, alert))

			tasks = []
			for key, [response, indices] in requestMap.items():
				payload = await response
				for i in indices:
					(authorId, accountId, alert) = alerts[i]
					tasks.append(create_task(self.check_price_alert(payload, authorId, accountId, alert.reference, alert.to_dict())))
			if len(tasks) > 0: await wait(tasks)

			print("Task finished in", time() - startTimestamp, "seconds")
		except (KeyboardInterrupt, SystemExit): pass
		except:
			print(format_exc())
			if environ["PRODUCTION"]: self.logging.report_exception()

	async def fetch_candles(self, session, alert):
		try:
			payload, message = {}, ""
			async with session.post(self.url + alert["currentPlatform"].lower(), json=alert["request"]) as response:
				data = await response.json()
				payload, message = data.get("response"), data.get("message")

			if not bool(payload):
				if message is not None:
					print("Alert request error:", message)
					if environ["PRODUCTION"]: self.logging.report(message)
				return { "candles": [] }
			return payload
		except:
			print(format_exc())
			if environ["PRODUCTION"]: self.logging.report_exception()
			return { "candles": [] }

	async def check_price_alert(self, payload, authorId, accountId, reference, alert):
		try:
			ticker = alert["request"].get("ticker")
			exchangeName = f" ({ticker.get('exchange').get('name')})" if ticker.get("exchange") else ''

			if alert["timestamp"] < time() - 86400 * 30.5 * 3:
				if environ["PRODUCTION"]:
					await database.document(f"discord/properties/messages/{str(uuid4())}").set({
						"title": f"Price alert for {ticker.get('name')}{exchangeName} at {alert.get('levelText', alert['level'])}{'' if ticker.get('quote') is None else ' ' + ticker.get('quote')} expired.",
						"subtitle": "Price Alerts",
						"description": "Price alerts automatically cancel after 3 months. If you'd like to keep your alert, you'll have to schedule it again.",
						"color": 6765239,
						"user": authorId,
						"channel": alert.get("channel"),
						"backupUser": authorId,
						"backupChannel": alert.get("backupChannel"),
						"botId": alert.get("botId", "401328409499664394")
					})
					await reference.delete()

				else:
					print(f"{accountId}: price alert for {ticker.get('name')}{exchangeName} at {alert.get('levelText', alert['level'])}{'' if ticker.get('quote') is None else ' ' + ticker.get('quote')} expired")

			else:
				for candle in reversed(payload["candles"]):
					if candle[0] < alert["timestamp"]: break
					if (alert["placement"] == "below" and candle[3] is not None and candle[3] <= alert["level"]) or (alert["placement"] == "above" and candle[2] is not None and alert["level"] <= candle[2]):
						if environ["PRODUCTION"]:
							await database.document(f"discord/properties/messages/{str(uuid4())}").set({
								"title": f"Price of {ticker.get('name')}{exchangeName} hit {alert.get('levelText', alert['level'])}{'' if ticker.get('quote') is None else ' ' + ticker.get('quote')}.",
								"description": alert.get("triggerMessage"),
								"tag": alert.get("triggerTag"),
								"subtitle": "Price Alerts",
								"color": 6765239,
								"user": authorId if alert["channel"] is None else None,
								"channel": alert.get("channel"),
								"backupUser": authorId,
								"backupChannel": alert.get("backupChannel"),
								"botId": alert.get("botId", "401328409499664394")
							})
							await reference.delete()

						else:
							print(f"{accountId}: price of {ticker.get('name')}{exchangeName} hit {alert.get('levelText', alert['level'])}{'' if ticker.get('quote') is None else ' ' + ticker.get('quote')}")
						break

		except (KeyboardInterrupt, SystemExit): pass
		except:
			print(format_exc())
			if environ["PRODUCTION"]: self.logging.report_exception(user=f"{accountId}, {authorId}")


	# -------------------------
	# Halt Alerts
	# -------------------------

	def parse_halt_date(self, date):
		return datetime.strptime(date, "%m/%d/%Y %H:%M:%S").replace(tzinfo=EST).timestamp()

	def parse_halts(self, data):
		parsed = {}
		for halt in data:
			symbol = halt["ndaq_issuesymbol"].upper()
			timestamp = self.parse_halt_date(halt["ndaq_haltdate"] + " " + halt["ndaq_halttime"])
			resumption = None if halt["ndaq_resumptiondate"] == "" or halt["ndaq_resumptiontradetime"] == "" else self.parse_halt_date(halt["ndaq_resumptiondate"] + " " + halt["ndaq_resumptiontradetime"])

			if resumption is None and halt["ndaq_reasoncode"] == "LUDP":
				resumption = timestamp + 5 * 60

			if resumption is not None and resumption <= time():
				continue
			if symbol in parsed and parsed[symbol]["timestamp"] <= timestamp:
				continue

			parsed[symbol] = {
				"timestamp" : timestamp,
				"code": halt["ndaq_reasoncode"],
				"resumption": resumption,
				"hash": str(hash(f"{halt['ndaq_issuesymbol']}{halt['ndaq_haltdate']}{halt['ndaq_halttime']}{halt['ndaq_reasoncode']}{resumption}"))
			}
		return parsed

	async def process_halt_alerts(self, session):
		try:
			startTimestamp = time()

			data = parse("http://www.nasdaqtrader.com/rss.aspx?feed=tradehalts")
			halts = self.parse_halts(data.entries)

			if self.haltDataCache.get("timestamp") is not None:
				new = set(halts.keys()).difference(set(self.haltDataCache["halts"].keys()))
				old = set(self.haltDataCache["halts"].keys()).difference(set(halts.keys()))
			else:
				old = set()
				new = set()

			for symbol, halt in self.haltDataCache.get("halts", {}).items():
				if symbol not in halts or halts[symbol]["hash"] == halt["hash"]:
					continue
				new.add(symbol)

			guilds = database.collection("details/feeds/halts").stream()
			async for guild in guilds:
				guildId = guild.id
				if guildId not in self.haltMessageCache:
					self.haltMessageCache[guildId] = {}

				feed = guild.to_dict()
				name, avatar = NAMES.get(feed.get("botId", "401328409499664394"), (MISSING, MISSING))
				webhook = Webhook.from_url(feed["url"], session=session)

				for symbol in new:
					message = self.haltMessageCache[guildId].pop(symbol, None)
					config = HALT_MAP.get(halts[symbol]['code'])
					if config is None: continue

					files = []
					if not config.get('halt', True):
						embed = Embed(title=f"{config.get('title')} (code: `{halts[symbol]['code']}`)", color=constants.colors["red"])
						if config.get("description") is not None:
							embed.add_field(name="Description", value=config.get("description"), inline=False)
						if halts[symbol]["resumption"] is not None:
							embed.add_field(name="Resumption time", value=f"<t:{int(halts[symbol]['resumption'])}> (<t:{int(halts[symbol]['resumption'])}:R>)", inline=False)

					else:
						guildProperties = await self.guildProperties.get(guildId, {})
						accountId = guildProperties.get("settings", {}).get("setup", {}).get("connection")
						userProperties = await self.accountProperties.get(accountId, {})

						if guildProperties.get("stale", {}).get("count", 0) > 0: continue

						request = CommandRequest(
							accountId=accountId,
							authorId=userProperties.get("oauth", {}).get("discord", {}).get("userId"),
							guildId=guildId,
							accountProperties=userProperties,
							guildProperties=guildProperties
						)

						platforms = request.get_platform_order_for("c")
						arguments = [] if config.get("chart") is None else ["5m" if config.get("chart") == "low" else "1d"]
						responseMessage, task = await process_chart_arguments(arguments, platforms, tickerId=f"NASDAQ:{symbol}")

						if responseMessage is not None:
							print(responseMessage)
							continue

						currentTask = task.get(task.get("currentPlatform"))
						timeframes = task.pop("timeframes")
						for p, t in timeframes.items(): task[p]["currentTimeframe"] = t[0]

						if message is None:
							payload, responseMessage = None, None
							if config.get("chart"):
								payload, responseMessage = await process_task(task, "chart")

							if payload is not None:
								task["currentPlatform"] = payload.get("platform")
								currentTask = task.get(task.get("currentPlatform"))
								files.append(File(payload.get("data"), filename="{:.0f}-{}-{}.png".format(time() * 1000, request.authorId, randint(1000, 9999))))

						pastEvents = message.embeds[0].fields[0].value if message is not None else ""
						if halts[symbol]['code'] == self.haltDataCache["halts"][symbol]["code"]:
							timeline = pastEvents
						else:
							timeline = pastEvents + f"\n{config.get('title')} (code: `{halts[symbol]['code']}`) <t:{int(halts[symbol]['timestamp'])}:R>"

						embed = Embed(title=f"Trading for {currentTask.get('ticker').get('name')} (`{currentTask.get('ticker').get('id')}`) has been halted.", color=constants.colors["red"])
						embed.add_field(name="Timeline", value=timeline.strip(), inline=False)
						if config.get("description") is not None:
							embed.add_field(name="Description", value=config.get("description"), inline=False)
						if halts[symbol]["resumption"] is not None:
							embed.add_field(name="Resumption time", value=f"<t:{int(halts[symbol]['resumption'])}> (<t:{int(halts[symbol]['resumption'])}:R>)", inline=False)

					if environ["PRODUCTION"] or guildId == "414498292655980583":
						try:
							if message is not None:
								message = await message.edit(
									embed=embed
								)
							else:
								message = await webhook.send(
									files=files,
									embed=embed,
									username=name,
									avatar_url=avatar,
									wait=True
								)
							self.haltMessageCache[guildId][symbol] = message
						except NotFound:
							await guild.reference.delete()

				for symbol in old:
					message = self.haltMessageCache[guildId].pop(symbol, None)
					config = HALT_MAP.get(self.haltDataCache["halts"][symbol]['code'])
					if config is None: continue
					if self.haltDataCache["halts"][symbol]['code'].startswith("IPO"): continue

					if not config.get('halt', True):
						embed = Embed(title=f"Market wide halt has been lifted.", color=constants.colors["green"])

					else:
						guildProperties = await self.guildProperties.get(guildId, {})
						accountId = guildProperties.get("settings", {}).get("setup", {}).get("connection")
						userProperties = await self.accountProperties.get(accountId, {})

						if guildProperties.get("stale", {}).get("count", 0) > 0: continue

						request = CommandRequest(
							accountId=accountId,
							authorId=userProperties.get("oauth", {}).get("discord", {}).get("userId"),
							guildId=guildId,
							accountProperties=userProperties,
							guildProperties=guildProperties
						)

						files = []
						platforms = request.get_platform_order_for("c")
						responseMessage, task = await process_chart_arguments([], platforms, tickerId=f"NASDAQ:{symbol}")

						if responseMessage is not None:
							print(responseMessage)
							continue

						currentTask = task.get(task.get("currentPlatform"))

						pastEvents = message.embeds[0].fields[0].value if message is not None else ""
						if self.haltDataCache['halts'][symbol]['resumption'] is None:
							timeline = pastEvents + f"\nTrading resumed <t:{int(time())}:R>"
						else:
							timeline = pastEvents + f"\nTrading resumed <t:{int(self.haltDataCache['halts'][symbol]['resumption'])}:R>"

						embed = Embed(title=f"Trading for {currentTask.get('ticker').get('name')} (`{currentTask.get('ticker').get('id')}`) has been resumed.", color=constants.colors["green"])
						embed.add_field(name="Timeline", value=timeline.strip(), inline=False)
						embed.add_field(name="Description", value="Trading has resumed.", inline=False)

					if environ["PRODUCTION"] or guildId == "414498292655980583":
						try:
							if message is not None:
								await message.edit(
									embed=embed
								)
							else:
								await webhook.send(
									embed=embed,
									username=name,
									avatar_url=avatar,
									wait=True
								)
						except NotFound:
							await guild.reference.delete()

			self.haltDataCache = {
				"timestamp": time(),
				"halts": halts,
			}
			await database.document("details/halts").set(self.haltDataCache)

		except (KeyboardInterrupt, SystemExit): pass
		except:
			print(format_exc())
			if environ["PRODUCTION"]: self.logging.report_exception()


if __name__ == "__main__":
	alertsServer = AlertsServer()
	run(alertsServer.run())
