
 /**
  * @name MissionDataMgr.h
  *   memory object caching system for managing and saving ingame data specific to missions
  *
  * @Author:        Allan
  * @date:      24 June 2018
  *
  */


#ifndef _EVE_SERVER_MISSION_DATAMANAGER_H__
#define _EVE_SERVER_MISSION_DATAMANAGER_H__


#include "../eve-server.h"
#include "missions/MissionDB.h"


class Client;
class SystemManager;

class MissionDataMgr
: public Singleton< MissionDataMgr >
{
public:
    MissionDataMgr();
    ~MissionDataMgr();

    int                 Initialize();

    void                Clear();
    void                Close()                         { Clear(); }
    void                GetInfo();

    void                Process();

    void                AddMissionOffer(uint32 charID, MissionOffer& data);
    void                UpdateMissionData(uint32 charID, MissionOffer& data);
    void                RemoveMissionOffer(uint32 charID, MissionOffer& data);
    void                LoadMissionOffers(uint32 charID, std::vector<MissionOffer>& data);
    void                LoadAgentOffers(const uint32 agentID, std::map<uint32, MissionOffer>& data);
    void                CreateMissionOffer(uint8 typeID, uint8 level, uint8 raceID, bool important, MissionOffer& data);
    // SECMISSION-1: spawn the guarded site for an accepted encounter
    // mission and remember its warp-in point for WarpToLocation
    void                SpawnMissionSite(Client* pClient, MissionOffer& offer);
    bool                GetMissionSitePoint(uint32 charID, GPoint& point);
    // SECMISSION-M2: journal bookmarks for combat site + agent turn-in
    void                BuildEncounterBookmarks(MissionOffer& offer, const GPoint& sitePoint, uint16 siteTypeID);
    // SECMISSION-M2: custom prose for missionID >= 56000 (empty = use briefingID).
    // Backed by the qstKill.briefing TEXT column -- editable without a rebuild.
    std::string         GetCustomBriefing(uint16 missionID);
    // SECMISSION-M3: what the site's leader says when the pilot lands.
    std::string         GetLeaderLine(uint16 missionID);
    // SECMISSION-M3: tag an NPC so its wreck carries the mission goal item.
    // Called by SpawnMissionSite for the transport; consumed by NPC::Killed.
    void                RegisterMissionDrop(uint32 npcItemID, uint16 goalTypeID, uint16 goalQty);
    // SECMISSION-M3: if this NPC was tagged, drop the mission objective.
    // M3i: drops a jettisoned cargo container beside the kill (the retail
    // shape, and the loot path proven reliable in live testing) -- wreck
    // inventory injection showed full-but-empty wrecks on the live client.
    // Returns true if the objective dropped.
    bool                InjectMissionLoot(uint32 npcItemID, SystemManager* pSysMgr, const GPoint& pos);
    // SECMISSION-M3b: acceleration-gate plumbing.  KeeperService's
    // ActivateAccelerationGate consults this to warp the pilot to the pocket.
    void                RegisterMissionGate(uint32 gateItemID, uint16 missionID, const GPoint& pocket);
    bool                GetMissionGatePocket(uint32 gateItemID, GPoint& pocket, uint16& missionID);

    std::string         GetTypeName(uint8 typeID);
    std::string         GetTypeLabel(uint8 typeID);

    PyString* GetKillRes()                               { PyIncRef(KillPNG); return KillPNG; }
    PyString* GetMiningRes()                             { PyIncRef(MiningPNG); return MiningPNG; }
    PyString* GetCourierRes()                            { PyIncRef(CourierPNG); return CourierPNG; }

protected:
    void                Populate();

private:
    uint8 m_procCount;

    std::map<std::string, uint32> m_names;
    std::multimap<uint8, CourierData> m_courier;    // level/data
    std::multimap<uint8, CourierData> m_courierImp;    // level/data
    std::multimap<uint8, CourierData> m_kill;       // level/data  (SECMISSION-1)
    std::multimap<uint8, CourierData> m_killImp;    // level/data  (SECMISSION-1)
    std::map<uint32, GPoint> m_sitePoints;          // charID/site (SECMISSION-1)
    // SECMISSION-M2: missionID -> prose loaded from qstKill.briefing/leaderLine.
    // Keyed by missionID (not level) so the journal can resolve text for an
    // offer restored from agtOffers after a restart, where only the id survives.
    struct KillText { std::string briefing; std::string leaderLine; uint8 level; };
    std::map<uint16, KillText> m_killText;          // missionID/prose (SECMISSION-M2)
    // SECMISSION-M3: npcItemID -> goal item its wreck must contain.
    struct MissionDrop { uint16 typeID; uint16 qty; };
    std::map<uint32, MissionDrop> m_missionDrops;   // npcItemID/drop (SECMISSION-M3)
    // SECMISSION-M3b: acceleration gate -> the deadspace pocket it serves.
    struct GatePocket { GPoint point; uint16 missionID; };
    std::map<uint32, GatePocket> m_gatePockets;     // gateItemID/pocket (SECMISSION-M3b)
    std::multimap<uint8, CourierData> m_mining;     // level/data
    std::multimap<uint8, CourierData> m_miningImp;     // level/data
    std::multimap<uint8, MissionData> m_missions;   // level/data
    std::multimap<uint8, MissionData> m_missionsImp;   // level/data
    std::multimap<uint32, MissionOffer> m_offers;   // charID/data      current mission offers by charID
    std::multimap<uint32, MissionOffer> m_aoffers;   // agentID/data    current mission offers by agentID
    std::multimap<uint32, MissionOffer> m_xoffers;   // charID/data     expired/completed offers by charID

    //  mission png resources...
    PyString* CourierPNG;
    PyString* MiningPNG;
    PyString* KillPNG;

};

//Singleton
#define sMissionDataMgr \
( MissionDataMgr::get() )


#endif  // _EVE_SERVER_MISSION_DATAMANAGER_H__
