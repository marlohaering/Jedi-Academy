-- Companion bot: while at least one human is on the server, a bot named BOT plays along; when the last
-- human leaves, the bot is kicked again. Needs bot_enable 1 (server.cfg); the bot's personality, model
-- and the map waypoints (botroutes/mp/*.wnt) come from the stock assets.
-- Polled from the frame loop instead of the connect/disconnect events: the disconnect event fires
-- while the leaving client still counts, and map changes reconnect everyone.
local plugin = RegisterPlugin('Companion', '1.0.0')

local BOT_NAME = 'BOT'
local BOT_FILE = 'Kyle Katarn'  -- name of a botfiles/bots.txt entry (personality, model, saber)
local BOT_SKILL = 3             -- 1-5
local CHECK_MS = 1000
local ADD_RETRY_MS = 10000      -- addbot is queued; don't add a second one while the first is joining

local nextCheck = 0
local lastAdd = -ADD_RETRY_MS

local function isCompanion(ply)
	return ply.isBot and ply.name:gsub('%^%w', '') == BOT_NAME
end

AddListener('JPLUA_EVENT_RUNFRAME', function()
	local now = GetTime()
	if now < nextCheck then return end
	nextCheck = now + CHECK_MS

	local humans, bots = 0, {}
	for _, ply in pairs(GetPlayers()) do
		if not ply.isBot then
			humans = humans + 1
		elseif isCompanion(ply) then
			bots[#bots + 1] = ply
		end
	end

	if humans > 0 then
		if #bots == 0 and (now - lastAdd >= ADD_RETRY_MS or now < lastAdd) then
			lastAdd = now
			-- addbot <botname> [skill] [team] [msec delay] [altname]; 2 = EXEC_APPEND
			SendConsoleCommand(2, string.format('addbot "%s" %d free 0 %s', BOT_FILE, BOT_SKILL, BOT_NAME))
		end
		for i = 2, #bots do bots[i]:Kick('left') end  -- never more than one
	else
		for _, bot in ipairs(bots) do bot:Kick('left') end
	end
end)
