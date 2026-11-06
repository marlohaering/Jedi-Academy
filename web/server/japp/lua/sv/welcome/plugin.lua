-- Welcome message (message of the day) for players who just joined, and /ammotd to show it again.
-- The text comes from the server cvar welcome_motd (server.cfg); "\n" starts a new line.
-- It is shown as a centre print for SHOW_MS (repeated, since the stock client fades centre prints
-- after cg_centertime seconds) and also printed into the console.
local plugin = RegisterPlugin('Welcome', '1.0.0')

local SHOW_MS = 9000
local REPEAT_MS = 2500
local showing = {}   -- clientNum -> { untilTime, nextTime }
local greeted = {}   -- clientNum -> true once greeted this session (not again on map changes)

local function motd()
	local cv = GetCvar('welcome_motd')
	local text = cv and cv:GetString() or ''
	return (text:gsub('\\n', '\n'):gsub('"', "'"))
end

local function show(id)
	local text = motd()
	if text == '' then return end
	SendReliableCommand(id, 'print "' .. text .. '\n"')
	SendReliableCommand(id, 'cp "' .. text .. '"')
	local now = GetTime()
	showing[id] = { untilTime = now + SHOW_MS, nextTime = now + REPEAT_MS }
end

AddListener('JPLUA_EVENT_CLIENTBEGIN', function(ply)
	if not greeted[ply.id] then
		greeted[ply.id] = true
		show(ply.id)
	end
end)

AddListener('JPLUA_EVENT_CLIENTDISCONNECT', function(ply)
	greeted[ply.id] = nil
	showing[ply.id] = nil
end)

AddListener('JPLUA_EVENT_RUNFRAME', function()
	local now = GetTime()
	for id, s in pairs(showing) do
		if now >= s.untilTime then
			showing[id] = nil
		elseif now >= s.nextTime then
			s.nextTime = now + REPEAT_MS
			SendReliableCommand(id, 'cp "' .. motd() .. '"')
		end
	end
end)

AddClientCommand('ammotd', function(ply, args)
	show(ply.id)
end)
