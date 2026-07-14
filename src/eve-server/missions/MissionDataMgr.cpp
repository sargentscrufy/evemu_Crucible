
 /**
  * @name MissionDataMgr.cpp
  *   memory object caching system for managing and saving ingame data specific to missions
  *
  * @Author:        Allan
  * @date:      24 June 2018
  *
  */
#include "../EVEServerConfig.h"

#include "Client.h"
#include "EntityList.h"
#include "agents/Agent.h"
#include "agents/AgentMgrService.h"
#include "database/EVEDBUtils.h"
#include "missions/MissionDataMgr.h"
#include "inventory/ItemFactory.h"
#include "map/MapData.h"
#include "system/SystemManager.h"
#include "system/Container.h"
#include "StaticDataMgr.h"

MissionDataMgr::MissionDataMgr()
{
    m_procCount = 0;
    m_names.clear();
    m_offers.clear();
    m_mining.clear();
    m_courier.clear();
    m_xoffers.clear();
    m_missions.clear();
}

MissionDataMgr::~MissionDataMgr()
{
    PyDecRef(KillPNG);
    PyDecRef(MiningPNG);
    PyDecRef(CourierPNG);
}

void MissionDataMgr::Clear()
{
    m_names.clear();
    m_offers.clear();
    m_mining.clear();
    m_courier.clear();
    m_xoffers.clear();
    m_missions.clear();
    // SECMISSION-1/M2/M3: these were never cleared -- a second Populate() would
    // have stacked duplicate encounter sets on top of the existing ones.
    m_kill.clear();
    m_killImp.clear();
    m_killText.clear();
    m_sitePoints.clear();
    m_missionDrops.clear();
    m_courierImp.clear();
    m_miningImp.clear();
    m_missionsImp.clear();
    m_aoffers.clear();
}

int MissionDataMgr::Initialize()
{
    Populate();
    sLog.Blue("   MissionDataMgr", "Mission Data Manager Initialized.");
    return 1;
}

void MissionDataMgr::GetInfo()
{
    // not used yet
}

// called every minute from EntityList::Process()
void MissionDataMgr::Process()
{
    // process open offers every 5m
    if (++m_procCount > 5) {
        m_procCount = 0;

        Agent* pAgent(nullptr);
        Client* pClient(nullptr);
        std::multimap<uint32, MissionOffer>::iterator itr = m_offers.begin();
        while (itr != m_offers.end()) {
            if (itr->second.expiryTime < GetFileTimeNow()) {
                pAgent = sEntityList.GetAgent(itr->second.agentID);
                pClient = sEntityList.FindClientByCharID(itr->first);
                // notify client if they are online.  eventaully we'll send mail also
                if (itr->second.stateID == Mission::State::Accepted) {
                    pAgent->SendMissionUpdate(pClient, "failed");
                    itr->second.stateID = Mission::State::Failed;
                    if (itr->second.courierTypeID) {
                        // remove item from player's possession
                        if (pClient != nullptr) {
                            pClient->RemoveMissionItem(itr->second.courierTypeID, itr->second.courierAmount);
                        } else {
                            MissionDB::RemoveMissionItem(itr->first, itr->second.courierTypeID, itr->second.courierAmount);
                        }
                    }
                } else if (itr->second.stateID == Mission::State::Offered) {
                    pAgent->SendMissionUpdate(pClient, "offer_expired");
                    itr->second.stateID = Mission::State::Expired;
                }
                std::multimap<uint32, MissionOffer>::iterator itr2 = m_aoffers.find(itr->second.agentID);
                if (itr2 != m_aoffers.end())
                    m_aoffers.erase(itr2);
                m_xoffers.emplace(itr->first, itr->second);
                pAgent->RemoveOffer(itr->first);
                MissionDB::UpdateMissionOffer(itr->second);
                itr = m_offers.erase(itr);
                pAgent = nullptr;
                pClient = nullptr;
            } else {
                ++itr;
            }
        }
    }
}


void MissionDataMgr::Populate()
{
    double start = GetTimeMSeconds();
    double begin = GetTimeMSeconds();

    CourierPNG = new PyString("<img src='res:/UI/netres/mission_content/couriermission.png' align=center hspace=4 vspace=4>");
    MiningPNG = new PyString("<img src='res:/UI/netres/mission_content/miningmission.png' align=center hspace=4 vspace=4>");
    KillPNG = new PyString("<img src='res:/UI/netres/mission_content/killmission.png' align=center hspace=4 vspace=4>");
    /*  not sure if these are used/needed....
    PNG = new PyString("<img src='res:/UI/netres/mission_content/agent_interaction.png' align=center hspace=4 vspace=4>");
    PNG = new PyString("<img src='res:/UI/netres/mission_content/agent_talkto.png' align=center hspace=4 vspace=4>");
    PNG = new PyString("<img src='res:/UI/netres/mission_content/arc_amarr.png' align=center hspace=4 vspace=4>");
    PNG = new PyString("<img src='res:/UI/netres/mission_content/arc_caldari.png' align=center hspace=4 vspace=4>");
    PNG = new PyString("<img src='res:/UI/netres/mission_content/arc_gallente.png' align=center hspace=4 vspace=4>");
    PNG = new PyString("<img src='res:/UI/netres/mission_content/arc_minmatar.png' align=center hspace=4 vspace=4>");
    PNG = new PyString("<img src='res:/UI/netres/mission_content/arc_npe.png' align=center hspace=4 vspace=4>");
    PNG = new PyString("<img src='res:/UI/netres/mission_content/blood_stained.png' align=center hspace=4 vspace=4>");
    PNG = new PyString("<img src='res:/UI/netres/mission_content/angels_and_artifacts.png' align=center hspace=4 vspace=4>");
    PNG = new PyString("<img src='res:/UI/netres/mission_content/smash_and_grab.png' align=center hspace=4 vspace=4>");
    */

    DBQueryResult* res = new DBQueryResult();
    DBResultRow row;

    MissionDB::LoadCourierData(*res);
    while (res->GetRow(row)) {
        //SELECT id, briefingID, name, level, typeID, important, storyline, itemTypeID, itemQty, rewardISK, rewardItemID, rewardItemQty, bonusISK, bonusTime, sysRange, raceID FROM qstCourier
        CourierData data = CourierData();
        data.missionID     = row.GetInt(0);
        data.briefingID    = row.GetInt(1);
        data.name          = row.GetText(2);
        data.level         = row.GetInt(3);
        data.typeID        = row.GetInt(4);
        data.important     = row.GetBool(5);
        data.storyline     = row.GetBool(6);
        data.itemTypeID    = row.GetInt(7);
        data.itemQty       = row.GetInt(8);
        data.itemVolume    = row.GetFloat(9);
        data.rewardISK     = row.GetInt(10);
        data.rewardItemID  = row.GetInt(11);
        data.rewardItemQty = row.GetInt(12);
        data.bonusISK      = row.GetInt(13);
        data.bonusTime     = row.GetInt(14);
        data.range         = row.GetInt(15);
        data.raceID        = row.GetInt(16);
        if (data.important) {
            m_courierImp.emplace(row.GetInt(3), data);
        } else {
            m_courier.emplace(row.GetInt(3), data);
        }
    }
    sLog.Cyan("   MissionDataMgr", "%lu(%lu) Courier Mission Data Sets loaded in %.3fms.", m_courier.size(), m_courierImp.size(),(GetTimeMSeconds() - start));

    //res->Reset();
    start = GetTimeMSeconds();
    MissionDB::LoadMiningData(*res);
    while (res->GetRow(row)) {
        //SELECT id, briefingID, name, level, typeID, important, storyline, itemTypeID, itemQty, rewardISK, rewardItemID, rewardItemQty, bonusISK, bonusTime, sysRange, raceID FROM qstMining
        CourierData data = CourierData();
        data.missionID     = row.GetInt(0);
        data.briefingID    = row.GetInt(1);
        data.name          = row.GetText(2);
        data.level         = row.GetInt(3);
        data.typeID        = row.GetInt(4);
        data.important     = row.GetBool(5);
        data.storyline     = row.GetBool(6);
        data.itemTypeID    = row.GetInt(7);
        data.itemQty       = row.GetInt(8);
        data.itemVolume    = row.GetFloat(9);
        data.rewardISK     = row.GetInt(10);
        data.rewardItemID  = row.GetInt(11);
        data.rewardItemQty = row.GetInt(12);
        data.bonusISK      = row.GetInt(13);
        data.bonusTime     = row.GetInt(14);
        data.range         = row.GetInt(15);
        data.raceID        = row.GetInt(16);
        if (data.important) {
            m_miningImp.emplace(row.GetInt(3), data);
        } else {
            m_mining.emplace(row.GetInt(3), data);
        }
    }
    sLog.Cyan("   MissionDataMgr", "%lu(%lu) Mining Mission Data Sets loaded in %.3fms.", m_mining.size(), m_miningImp.size(), (GetTimeMSeconds() - start));

    // SECMISSION-1: encounter (security/kill) mission sets from qstKill
    start = GetTimeMSeconds();
    MissionDB::LoadKillData(*res);
    while (res->GetRow(row)) {
        CourierData data = CourierData();
        data.missionID     = row.GetInt(0);
        data.briefingID    = row.GetInt(1);
        data.name          = row.GetText(2);
        data.level         = row.GetInt(3);
        data.typeID        = row.GetInt(4);
        data.important     = row.GetBool(5);
        data.storyline     = row.GetBool(6);
        data.itemTypeID    = row.GetInt(7);
        data.itemQty       = row.GetInt(8);
        data.itemVolume    = row.GetFloat(9);
        data.rewardISK     = row.GetInt(10);
        data.rewardItemID  = row.GetInt(11);
        data.rewardItemQty = row.GetInt(12);
        data.bonusISK      = row.GetInt(13);
        data.bonusTime     = row.GetInt(14);
        data.range         = row.GetInt(15);
        data.raceID        = row.GetInt(16);
        // SECMISSION-M2: prose columns are nullable -- GetText on a NULL is a
        // null char* and would blow up std::string's ctor, so gate on IsNull.
        data.briefing      = row.IsNull(17) ? "" : row.GetText(17);
        data.leaderLine    = row.IsNull(18) ? "" : row.GetText(18);
        if (data.important) {
            m_killImp.emplace(row.GetInt(3), data);
        } else {
            m_kill.emplace(row.GetInt(3), data);
        }
        // index prose by missionID: an offer reloaded from agtOffers after a
        // restart carries the id but not the text, and the journal still has
        // to render it.
        if (!data.briefing.empty() or !data.leaderLine.empty()) {
            KillText kt;
            kt.briefing   = data.briefing;
            kt.leaderLine = data.leaderLine;
            kt.level      = data.level;
            m_killText[data.missionID] = kt;
        }
    }
    sLog.Cyan("   MissionDataMgr", "%lu(%lu) Encounter Mission Data Sets loaded in %.3fms.", m_kill.size(), m_killImp.size(), (GetTimeMSeconds() - start));

    start = GetTimeMSeconds();
    sLog.Cyan("   MissionDataMgr", "0(0) Storyline Mission Data Sets loaded in %.3fms.", (GetTimeMSeconds() - start));

    start = GetTimeMSeconds();
    sLog.Cyan("   MissionDataMgr", "0(0) Tutorial Mission Data Sets loaded in %.3fms.", (GetTimeMSeconds() - start));

    start = GetTimeMSeconds();
    sLog.Cyan("   MissionDataMgr", "0(0) Research Mission Data Sets loaded in %.3fms.", (GetTimeMSeconds() - start));

    start = GetTimeMSeconds();
    sLog.Cyan("   MissionDataMgr", "0(0) Anomic Mission Data Sets loaded in %.3fms.", (GetTimeMSeconds() - start));

    start = GetTimeMSeconds();
    sLog.Cyan("   MissionDataMgr", "0(0) Data Mission Data Sets loaded in %.3fms.", (GetTimeMSeconds() - start));

    start = GetTimeMSeconds();
    sLog.Cyan("   MissionDataMgr", "0(0) Trade Mission Data Sets loaded in %.3fms.", (GetTimeMSeconds() - start));

    start = GetTimeMSeconds();
    sLog.Cyan("   MissionDataMgr", "0(0) Burner Mission Data Sets loaded in %.3fms.", (GetTimeMSeconds() - start));

    start = GetTimeMSeconds();
    sLog.Cyan("   MissionDataMgr", "0(0) Cosmos Mission Data Sets loaded in %.3fms.", (GetTimeMSeconds() - start));

    start = GetTimeMSeconds();
    sLog.Cyan("   MissionDataMgr", "0(0) Arc Mission Data Sets loaded in %.3fms.", (GetTimeMSeconds() - start));

    //res->Reset();
    start = GetTimeMSeconds();
    MissionDB::LoadMissionData(*res);
    while (res->GetRow(row)) {
        //SELECT id, briefingID, name, level, typeID, important, storyline, raceID, constellationID, corporationID, dungeonID,
        // rewardISK, rewardItemID, rewardISKQty, rewardItemQty, bonusISK, bonusTime FROM agtMissions
        MissionData data = MissionData();
        data.missionID = row.GetInt(0);
        data.briefingID = row.GetInt(1);
        data.name = row.GetText(2);
        data.level = row.GetInt(3);
        data.typeID = row.GetInt(4);
        data.important = row.GetBool(5);
        data.constellationID = row.GetInt(8);
        data.corporationID = row.GetInt(9);
        data.dungeonID = row.GetInt(10);
        if (data.important) {
            m_missionsImp.emplace(row.GetInt(3), data);
        } else {
            m_missions.emplace(row.GetInt(3), data);
        }
    }
    sLog.Cyan("   MissionDataMgr", "%lu(%lu) Unsorted Mission Data Sets loaded in %.3fms.", m_missions.size(), m_missionsImp.size(), (GetTimeMSeconds() - start));

    //res->Reset();
    start = GetTimeMSeconds();
    MissionDB::LoadOpenOffers(*res);
    while (res->GetRow(row)) {
        //SELECT acceptFee, agentID, characterID, courierAmount, courierTypeID, courierItemVolume, dateAccepted, dateIssued, destinationID, destinationTypeID, destinationOwnerID, destinationSystemID,
        // expiryTime, important, storyline, missionID, briefingID, name, offerID, originID, originOwnerID, originSystemID, remoteCompletable, remoteOfferable,
        // rewardISK, rewardItemID, rewardItemQty, rewardLP, bonusISK, bonusTime, stateID, typeID, dungeonLocationID, dungeonSolarSystemID FROM agtOffers
        MissionOffer offer = MissionOffer();
        offer.acceptFee = row.GetInt(0);
        offer.agentID = row.GetInt(1);
        offer.characterID = row.GetInt(2);
        offer.courierAmount = row.GetInt(3);
        offer.courierTypeID = row.GetInt(4);
        offer.courierItemVolume = row.GetFloat(5);
        offer.dateAccepted = row.GetInt64(6);
        offer.dateIssued = row.GetInt64(7);
        offer.destinationID = row.GetInt(8);
        offer.destinationTypeID = row.GetInt(9);
        offer.destinationOwnerID = row.GetInt(10);
        offer.destinationSystemID = row.GetInt(11);
        offer.expiryTime = row.GetInt64(12);
        offer.important = row.GetInt(13);
        offer.storyline = row.GetInt(14);
        offer.missionID = row.GetInt(15);
        offer.briefingID = row.GetInt(16);
        offer.name = row.GetText(17);
        offer.offerID = row.GetInt(18);
        offer.originID = row.GetInt(19);
        offer.originOwnerID = row.GetInt(20);
        offer.originSystemID = row.GetInt(21);
        offer.remoteCompletable = row.GetInt(22);
        offer.remoteOfferable = row.GetInt(23);
        offer.rewardISK = row.GetInt(24);
        offer.rewardItemID = row.GetInt(25);
        offer.rewardItemQty = row.GetInt(26);
        offer.rewardLP = row.GetInt(27);
        offer.bonusISK = row.GetInt(28);
        offer.bonusTime = row.GetInt(29);
        offer.stateID = row.GetInt(30);
        offer.typeID = row.GetInt(31);
        offer.dungeonLocationID = row.GetInt(32);
        offer.dungeonSolarSystemID = row.GetInt(33);
        offer.dateCompleted = 0;
        // will need to determine how to store/retrieve bookmarks as a list of dicts here
        offer.bookmarks = new PyList();
        m_offers.emplace(row.GetInt(2), offer);
        m_aoffers.emplace(row.GetInt(1), offer);    // do we really want dupe data here?  yes.  need offer by char and by agent
    }
    sLog.Cyan("   MissionDataMgr", "%lu Open Mission Offers loaded in %.3fms.", m_offers.size(), (GetTimeMSeconds() - start));

    //res->Reset();
    start = GetTimeMSeconds();
    // config switch to allow loading/displaying of expired/completed mission offers
    if (sConfig.server.LoadOldMissions)
        MissionDB::LoadClosedOffers(*res);
    while (res->GetRow(row)) {
        //SELECT agentID, characterID, courierAmount, courierTypeID, dateAccepted, dateCompleted, dateIssued, destinationID, expiryTime, important, storyline, missionID, name,
        // offerID, originID, rewardISK, rewardItemID, rewardItemQty, rewardLP, stateID, typeID FROM agtOffers
        MissionOffer offer = MissionOffer();
        offer.agentID = row.GetInt(0);
        offer.characterID = row.GetInt(1);
        offer.courierAmount = row.GetInt(2);
        offer.courierTypeID = row.GetInt(3);
        offer.dateAccepted = row.GetInt64(4);
        offer.dateCompleted = row.GetInt64(5);
        offer.dateIssued = row.GetInt64(6);
        offer.destinationID = row.GetInt(7);
        offer.expiryTime = row.GetInt64(8);
        offer.important = row.GetInt(9);
        offer.storyline = row.GetInt(10);
        offer.missionID = row.GetInt(11);
        offer.name = row.GetText(12);
        offer.offerID = row.GetInt(13);
        offer.originID = row.GetInt(14);
        offer.rewardISK = row.GetInt(15);
        offer.rewardItemID = row.GetInt(16);
        offer.rewardItemQty = row.GetInt(17);
        offer.rewardLP = row.GetInt(18);
        offer.stateID = row.GetInt(19);
        offer.typeID = row.GetInt(20);
        offer.briefingID = 0;
        offer.acceptFee = 0;
        offer.bonusISK = 0;
        offer.bonusTime = 0;
        offer.remoteCompletable = 0;
        offer.remoteOfferable = 0;
        offer.originOwnerID = 0;
        offer.originSystemID = 0;
        offer.destinationTypeID = 0;
        offer.destinationOwnerID = 0;
        offer.destinationSystemID = 0;
        offer.dungeonLocationID = 0;
        offer.dungeonSolarSystemID = 0;
        offer.bookmarks = new PyList(); //invalid offers will not have bms
        m_xoffers.emplace(row.GetInt(2), offer);
    }
    sLog.Cyan("   MissionDataMgr", "%lu Closed Mission Offers loaded in %.3fms.", m_xoffers.size(), (GetTimeMSeconds() - start));

    // cleanup
    SafeDelete(res);
/*
    m_names.emplace("Arisite Envy",   45000 );
    m_names.emplace("Asteroid Catastrophe",    1080 );
    m_names.emplace("Better World", 6000    );
    m_names.emplace("Beware They Live",    9000   );
    m_names.emplace("Bountiful Bandine",   2000         );
    m_names.emplace("Burnt Traces",    1080           );
    m_names.emplace("Cheap Chills",    20000  );
    m_names.emplace("Claimjumpers",    1800       );
    m_names.emplace("Data Mining", 299   );
    m_names.emplace("Down and Dirty",  2250       );
    m_names.emplace("Drone Distribution",  4000   );
    m_names.emplace("Feeding the Giant",   44800 );
    m_names.emplace("Gas Injections",  4250  );
    m_names.emplace("Geodite and Gemology",    44800 );
    m_names.emplace("Ice Installation",    20000  );
    m_names.emplace("Like Drones to a Cloud",  4250 );
    m_names.emplace("Mercium Belt",    6000   );
    m_names.emplace("Mercium Experiments", 1080     );
    m_names.emplace("Mother Lode", 44800  );
    m_names.emplace("Not Gneiss at All",   45000 );
    m_names.emplace("Pile of Pithix",  9000   );
    m_names.emplace("Persistent Pests",    4000   );
    m_names.emplace("Starting Simple", 2000     );
    m_names.emplace("Stay Frosty", 10000   );
    m_names.emplace("Understanding Augmene",   2625  );
    m_names.emplace("Unknown Events",  6000 );
    */
    sLog.Cyan("   MissionDataMgr", "Mission Data loaded in %.3fms.", (GetTimeMSeconds() - begin));
}

void MissionDataMgr::AddMissionOffer(uint32 charID, MissionOffer& data)
{
    m_offers.emplace(charID, data);
    m_aoffers.emplace(data.agentID, data);
}

void MissionDataMgr::RemoveMissionOffer(uint32 charID, MissionOffer& data)
{
    auto itr = m_offers.equal_range(charID);
    for (auto it = itr.first; it != itr.second; ++it)
        if (it->second.agentID == data.agentID) {
            m_offers.erase(it);
            break;
        }

    itr = m_aoffers.equal_range(data.agentID);
    for (auto it = itr.first; it != itr.second; ++it)
        if (it->second.characterID == charID) {
            m_aoffers.erase(it);
            break;
        }
}

void MissionDataMgr::LoadAgentOffers(const uint32 agentID, std::map< uint32, MissionOffer >& data)
{
    auto itr = m_aoffers.equal_range(agentID);
    for (auto it = itr.first; it != itr.second; ++it)
        data[it->second.characterID] = (it->second);
}

void MissionDataMgr::LoadMissionOffers(uint32 charID, std::vector<MissionOffer>& data)
{
    auto itr = m_offers.equal_range(charID);
    for (auto it = itr.first; it != itr.second; ++it)
        data.push_back(it->second);

    // config switch to allow loading/displaying of expired/completed mission offers
    // not completely working yet.....AgentMgrService::Handle_GetMyJournalDetails() will need work to implement this.
    if (sConfig.server.LoadOldMissions) {
        auto itr = m_xoffers.equal_range(charID);
        for (auto it = itr.first; it != itr.second; ++it)
            data.push_back(it->second);
    }
}

void MissionDataMgr::CreateMissionOffer(uint8 typeID, uint8 level, uint8 raceID, bool important, MissionOffer& data)
{
    // variable mission data based on agent, init to 0 here.
    data.stateID                = Mission::State::Allocated;
    data.dateIssued             = GetFileTimeNow();
    data.remoteOfferable        = false;
    data.remoteCompletable      = false;
    data.range                  = 0;
    data.offerID                = 0;
    data.agentID                = 0;
    data.rewardLP               = 0;
    data.originID               = 0;
    data.originOwnerID          = 0;
    data.originSystemID         = 0;
    data.acceptFee              = 0;
    data.expiryTime             = 0;
    data.characterID            = 0;
    data.dateAccepted           = 0;
    data.dateCompleted          = 0;
    data.destinationID          = 0;
    data.destinationTypeID      = 0;
    data.destinationOwnerID     = 0;
    data.destinationSystemID    = 0;
    data.dungeonLocationID      = 0;
    data.dungeonSolarSystemID   = 0;
    data.bookmarks              = new PyList();

    /** @todo  this will need to be adjusted for raceID eventually */
    switch (typeID) {
        case Mission::Type::Courier: {
            CourierData cData = CourierData();
            std::vector<CourierData> cVec;
            if (important) {
                auto itr = m_courierImp.equal_range(level);
                for (auto it = itr.first; it != itr.second; ++it)
                    cVec.push_back(it->second);
            } else {
                auto itr = m_courier.equal_range(level);
                for (auto it = itr.first; it != itr.second; ++it)
                    cVec.push_back(it->second);
            }
            cData = cVec[MakeRandomInt(0, (cVec.size() -1))];
            // verify mission race acceptable
            if ((cData.raceID) and ((cData.raceID & raceID) != raceID)) {
                for (auto cur :cVec) {
                    if ((cur.raceID & raceID) == raceID)
                        cData = cur;
                }
            }

            data.name               = cData.name;
            data.typeID             = cData.typeID;
            data.bonusISK           = cData.bonusISK;
            data.rewardISK          = cData.rewardISK;
            data.bonusTime          = cData.bonusTime;
            data.important          = cData.important;
            data.storyline          = cData.storyline;
            data.missionID          = cData.missionID;
            data.briefingID         = cData.briefingID;
            data.rewardItemID       = cData.rewardItemID;
            data.rewardItemQty      = cData.rewardItemQty;
            data.courierTypeID      = cData.itemTypeID;
            data.courierAmount      = cData.itemQty;
            data.courierItemVolume  = cData.itemVolume;
            data.range              = cData.range;
        } break;
        case Mission::Type::Mining: {
            CourierData cData = CourierData();
            std::vector<CourierData> cVec;
            if (important) {
                auto itr = m_miningImp.equal_range(level);
                for (auto it = itr.first; it != itr.second; ++it)
                    cVec.push_back(it->second);
            } else {
                auto itr = m_mining.equal_range(level);
                for (auto it = itr.first; it != itr.second; ++it)
                    cVec.push_back(it->second);
            }
            cData = cVec[MakeRandomInt(0, (cVec.size() -1))];

            data.name               = cData.name;
            data.typeID             = cData.typeID;
            data.bonusISK           = cData.bonusISK;
            data.rewardISK          = cData.rewardISK;
            data.bonusTime          = cData.bonusTime;
            data.important          = cData.important;
            data.storyline          = cData.storyline;
            data.missionID          = cData.missionID;
            data.briefingID         = cData.briefingID;
            data.rewardItemID       = cData.rewardItemID;
            data.rewardItemQty      = cData.rewardItemQty;
            data.courierTypeID      = cData.itemTypeID;
            data.courierAmount      = cData.itemQty;
            data.courierItemVolume  = cData.itemVolume;
            data.range              = cData.range;
        } break;
        case Mission::Type::Tutorial: {
        } break;
        case Mission::Type::Encounter: {
            // SECMISSION-1
            CourierData cData = CourierData();
            std::vector<CourierData> cVec;
            if (important) {
                auto itr = m_killImp.equal_range(level);
                for (auto it = itr.first; it != itr.second; ++it)
                    cVec.push_back(it->second);
            }
            if (cVec.empty()) {
                auto itr = m_kill.equal_range(level);
                for (auto it = itr.first; it != itr.second; ++it)
                    cVec.push_back(it->second);
            }
            if (cVec.empty()) {
                // no encounter content for this level -- fall back to courier
                _log(AGENT__WARNING, "CreateMissionOffer - no encounter sets for level %u; falling back to courier.", level);
                CreateMissionOffer(Mission::Type::Courier, level, raceID, important, data);
                return;
            }
            cData = cVec[MakeRandomInt(0, (cVec.size() -1))];

            data.name               = cData.name;
            data.typeID             = cData.typeID;
            data.bonusISK           = cData.bonusISK;
            data.rewardISK          = cData.rewardISK;
            data.bonusTime          = cData.bonusTime;
            data.important          = cData.important;
            data.storyline          = cData.storyline;
            data.missionID          = cData.missionID;
            data.briefingID         = cData.briefingID;
            data.rewardItemID       = cData.rewardItemID;
            data.rewardItemQty      = cData.rewardItemQty;
            data.courierTypeID      = cData.itemTypeID;
            data.courierAmount      = cData.itemQty;
            data.courierItemVolume  = cData.itemVolume;
            data.range              = cData.range;
        } break;
        case Mission::Type::Trade: {
        } break;
        case Mission::Type::Research: {
        } break;
        case Mission::Type::Data: {
        } break;
        case Mission::Type::Storyline: {
        } break;
        case Mission::Type::Cosmos: {
        } break;
        case Mission::Type::EpicArc: {
        } break;
        case Mission::Type::Anomic: {
        } break;
    }

    _log(AGENT__DEBUG, "Created %s level %u %s offer - '%s'", (important?"an important":"a"), level, GetTypeName(data.typeID).c_str(), data.name.c_str());
}


std::string MissionDataMgr::GetTypeName(uint8 typeID)
{
    using namespace Mission::Type;
    switch (typeID) {
        case Tutorial:          return "Tutorial";
        case Encounter:         return "Encounter";
        case Courier:           return "Courier";
        case Trade:             return "Trade";
        case Mining:            return "Mining";
        case Research:          return "Research";
        case Data:              return "Data";
        case Storyline:         return "Storyline";
        case Cosmos:            return "Cosmos";
        case EpicArc:           return "Arc";
        case Anomic:            return "Anomic";
        case Burner:            return "Burner";
        default:                return "Invalid";
    }
}

std::string MissionDataMgr::GetTypeLabel(uint8 typeID)
{
    using namespace Mission::Type;
    switch (typeID) {
        case Tutorial:          return "UI/Agents/MissionTypes/Tutorial";
        case Encounter:         return "UI/Agents/MissionTypes/Encounter";
        case Courier:           return "UI/Agents/MissionTypes/Courier";
        case Trade:             return "UI/Agents/MissionTypes/Trade";
        case Mining:            return "UI/Agents/MissionTypes/Mining";
        case Research:          return "UI/Agents/MissionTypes/Research";
        case Data:              return "UI/Agents/MissionTypes/Data";
        case Storyline:         return "UI/Agents/MissionTypes/Storyline";
        case Cosmos:            return "UI/Agents/MissionTypes/Cosmos";
        case EpicArc:           return "UI/Agents/MissionTypes/EpicArc";
        case Anomic:            return "UI/Agents/MissionTypes/Anomic";
        case Burner:            return "UI/Agents/MissionTypes/Burner";
        default:                return "Invalid";
    }
}

void MissionDataMgr::UpdateMissionData(uint32 charID, MissionOffer& data)
{
    auto itr = m_offers.equal_range(charID);
    for (auto it = itr.first; it != itr.second; ++it)
        if (it->second.agentID == data.agentID) {
            it->second = data;
            break;
        }

    itr = m_aoffers.equal_range(data.agentID);
    for (auto it = itr.first; it != itr.second; ++it)
        if (it->second.characterID == charID) {
            it->second = data;
            break;
        }
}

// SECMISSION-1: spawn the guarded mission site for an accepted encounter
// mission.  v1 model: a cargo container holding the goal item, guarded by a
// wing of level-appropriate rats, anchored at a deadspace point off a random
// planet in the agent's system.  Completion is the courier-style fetch check
// (return to the agent with the goal item), so no kill-tagging is needed --
// but the guards WILL be between the pilot and the loot.
void MissionDataMgr::SpawnMissionSite(Client* pClient, MissionOffer& offer)
{
    if (pClient == nullptr)
        return;

    SystemManager* pSysMgr = pClient->SystemMgr();
    if (pSysMgr == nullptr) {
        _log(AGENT__ERROR, "SpawnMissionSite - no system manager for %s", pClient->GetName());
        return;
    }

    uint32 systemID = pSysMgr->GetID();
    GPoint sitePoint = sMapData.GetRandPointOnPlanet(systemID);
    if (sitePoint.isZero()) {
        _log(AGENT__ERROR, "SpawnMissionSite - no planet point in system %u", systemID);
        return;
    }
    // push the site off the planet warp-in a bit so it reads as deadspace
    sitePoint.MakeRandomPointOnSphere(80000 + MakeRandomInt(0, 40000));

    // SECMISSION-M3b: retail two-room shape.  Room 1 (the warp-in) holds ONLY
    // the acceleration gate -- no hostiles at the warp-in, per the retail
    // spec.  The fight lives in a pocket 90-130 km away; the gate warps the
    // pilot there (KeeperService::ActivateAccelerationGate).
    // NOTE: must exceed minWarpDistance (150km) or the gate's WarpTo refuses
    GPoint pocketPoint(sitePoint);
    pocketPoint.MakeRandomPointOnSphere(170000 + MakeRandomInt(0, 60000));

    // SECMISSION-M3: the site is now shaped like a retail L1 encounter --
    //   leader + 2-4 henchmen + one transport that is holding the goods.
    // The objective is NOT a free-floating can any more: the transport is
    // tagged, and its WRECK carries the goal item (see InjectMissionLoot,
    // called from NPC::Killed).  Kill the escort, kill the hauler, loot it.
    const uint32 factionID = sDataMgr.GetRegionRatFaction(pClient->GetRegionID());
    const uint32 corpID    = sDataMgr.GetFactionCorp(factionID);

    // small helper so leader/henchmen/transport all spawn identically
    auto spawnHostile = [&](uint16 typeID, const GPoint& pos) -> uint32 {
        const ItemType* iType = sItemFactory.GetType(typeID);
        if (iType == nullptr) {
            _log(AGENT__ERROR, "SpawnMissionSite - unknown typeID %u", typeID);
            return 0;
        }
        const std::string name = iType->name();
        ItemData ratData(typeID, ownerSystem, systemID, flagNone, name.c_str(), pos);
        InventoryItemRef ratRef = sItemFactory.SpawnItem(ratData);
        if (ratRef.get() == nullptr) {
            _log(AGENT__ERROR, "SpawnMissionSite - failed to spawn typeID %u", typeID);
            return 0;
        }
        DBSystemDynamicEntity ratEnt = DBSystemDynamicEntity();
            ratEnt.categoryID = EVEDB::invCategories::Entity;
            ratEnt.groupID = iType->groupID();
            ratEnt.itemID = ratRef->itemID();
            ratEnt.itemName = name;
            ratEnt.typeID = typeID;
            ratEnt.position = pos;
            ratEnt.factionID = factionID;
            ratEnt.allianceID = factionID;
            ratEnt.corporationID = corpID;
            ratEnt.ownerID = corpID;
        pSysMgr->BuildDynamicEntity(ratEnt);
        return ratRef->itemID();
    };

    // scenery: non-interactive celestial props that dress the pocket up as
    // a pirate staging point (CelestialSE; Large Collidable Object group)
    auto spawnProp = [&](uint16 typeID, const GPoint& pos) {
        const ItemType* iType = sItemFactory.GetType(typeID);
        if (iType == nullptr)
            return;
        const std::string name = iType->name();
        ItemData propData(typeID, ownerSystem, systemID, flagNone, name.c_str(), pos);
        InventoryItemRef propRef = sItemFactory.SpawnItem(propData);
        if (propRef.get() == nullptr)
            return;
        DBSystemDynamicEntity propEnt = DBSystemDynamicEntity();
            propEnt.categoryID = EVEDB::invCategories::Celestial;
            propEnt.groupID = iType->groupID();
            propEnt.itemID = propRef->itemID();
            propEnt.itemName = name;
            propEnt.typeID = typeID;
            propEnt.position = pos;
            propEnt.allianceID = 0;
            propEnt.corporationID = 0;
            propEnt.factionID = 0;
            propEnt.ownerID = ownerSystem;
        pSysMgr->BuildDynamicEntity(propEnt);
    };

    // --- room 1: the acceleration gate ---------------------------------
    uint32 gateID = 0;
    {
        const ItemType* gType = sItemFactory.GetType(17831 /*Acceleration Gate*/);
        if (gType != nullptr) {
            ItemData gData(17831, ownerSystem, systemID, flagNone, "Acceleration Gate", sitePoint);
            InventoryItemRef gRef = sItemFactory.SpawnItem(gData);
            if (gRef.get() != nullptr) {
                DBSystemDynamicEntity gEnt = DBSystemDynamicEntity();
                    gEnt.categoryID = EVEDB::invCategories::Celestial;
                    gEnt.groupID = EVEDB::invGroups::Warp_Gate;
                    gEnt.itemID = gRef->itemID();
                    gEnt.itemName = "Acceleration Gate";
                    gEnt.typeID = 17831;
                    gEnt.position = sitePoint;
                    gEnt.ownerID = ownerSystem;
                pSysMgr->BuildDynamicEntity(gEnt);
                gateID = gRef->itemID();
            }
        }
    }
    if (gateID == 0) {
        // no gate = fall back to a single-room site at the warp-in point
        _log(AGENT__WARNING, "SpawnMissionSite - gate failed to spawn; using single-room site.");
        pocketPoint = sitePoint;
    } else {
        RegisterMissionGate(gateID, offer.missionID, pocketPoint);
    }

    // --- the pocket: scenery + the fight -------------------------------
    // a Guristas den: habitation module + storage silo
    GPoint propPos(pocketPoint);
    propPos.MakeRandomPointOnSphere(12000 + MakeRandomInt(0, 6000));
    spawnProp(21827 /*LCO Habitation Roadhouse*/, propPos);
    propPos = pocketPoint;
    propPos.MakeRandomPointOnSphere(9000 + MakeRandomInt(0, 5000));
    spawnProp(10788 /*Gas-Storage Silo*/, propPos);

    // SECMISSION-M4: escort composition scales with the mission's level.
    // L1: light frigates.  L2: frigates stiffened by Pithum cruisers.
    uint8 level = 1;
    {
        auto ktItr = m_killText.find(offer.missionID);
        if (ktItr != m_killText.end() and (ktItr->second.level > 0))
            level = ktItr->second.level;
    }

    // --- the transport: this is what is holding the objective ----------
    // Guristas Hauler.  Sits at the centre of the pocket; the pilot has to
    // get through the escort to reach it.
    uint32 transportID = spawnHostile(13717 /*Guristas Hauler*/, pocketPoint);
    if (transportID == 0) {
        _log(AGENT__ERROR, "SpawnMissionSite - transport failed to spawn; mission '%s' for %s would be uncompletable, aborting site.",
             offer.name.c_str(), pClient->GetName());
        return;
    }
    // tag it: its wreck will contain the goal item
    RegisterMissionDrop(transportID, offer.courierTypeID, offer.courierAmount);

    // --- the leader: the one who talks -------------------------------
    GPoint leaderPos(pocketPoint);
    leaderPos.MakeRandomPointOnSphere(3000 + MakeRandomInt(0, 2000));
    spawnHostile(17006 /*Pithi Wrecker*/, leaderPos);

    // --- the henchmen -------------------------------------------------
    // L1 is meant to be easy: 2-4 frigates, no webs/scrams.
    // L2 adds a pair of Pithum cruisers behind the frigate screen.
    static const uint16 henchTypes[] = { 16981 /*Pithi Arrogator*/, 16994 /*Pithi Imputor*/, 16996 /*Pithi Infiltrator*/ };
    static const uint16 cruiserTypes[] = { 16982 /*Pithum Ascriber*/, 16998 /*Pithum Nullifier*/, 17004 /*Pithum Silencer*/ };
    uint8 henchmen = 2 + MakeRandomInt(0, 2);
    for (uint8 i = 0; i < henchmen; ++i) {
        GPoint guardPos(pocketPoint);
        guardPos.MakeRandomPointOnSphere(8000 + MakeRandomInt(0, 7000));
        spawnHostile(henchTypes[MakeRandomInt(0, 2)], guardPos);
    }
    if (level >= 2) {
        uint8 cruisers = 1 + MakeRandomInt(0, 1);
        for (uint8 i = 0; i < cruisers; ++i) {
            GPoint cruPos(pocketPoint);
            cruPos.MakeRandomPointOnSphere(12000 + MakeRandomInt(0, 8000));
            spawnHostile(cruiserTypes[MakeRandomInt(0, 2)], cruPos);
        }
        henchmen += cruisers;   // for the spawn log
    }

    m_sitePoints[offer.characterID] = sitePoint;
    // the site's "location" is the ACCELERATION GATE (room 1) -- warp-to
    // lands at a safe, hostile-free warp-in; the gate takes you to the fight.
    offer.dungeonLocationID = (gateID ? gateID : transportID);
    offer.dungeonSolarSystemID = systemID;

    // SECMISSION-M2: journal Encounters / right-click locations need a real
    // bookmark list (was always empty PyList).  Site = pickup (source),
    // agent station = return drop-off (destination).
    BuildEncounterBookmarks(offer, sitePoint, (gateID ? 17831 : 13717));

    _log(AGENT__MESSAGE, "SpawnMissionSite - '%s' for %s: gate %u -> pocket (leader + %u henchmen + transport %u, drops %u x%u) in %u at (%.0f, %.0f, %.0f)",
         offer.name.c_str(), pClient->GetName(), gateID, henchmen, transportID,
         offer.courierTypeID, offer.courierAmount, systemID,
         sitePoint.x, sitePoint.y, sitePoint.z);
}

bool MissionDataMgr::GetMissionSitePoint(uint32 charID, GPoint& point)
{
    auto itr = m_sitePoints.find(charID);
    if (itr == m_sitePoints.end())
        return false;
    point = itr->second;
    return true;
}

// SECMISSION-M2: util.KeyVal bookmarks matching the courier dump shape in
// AgentMgrService::GetMyJournalDetails (itemID/typeID/agentID/hint/
// locationType/coords/solarsystemID/...).  Client routes warp via
// agentMgr.WarpToLocation using locationType + locationNumber.
void MissionDataMgr::BuildEncounterBookmarks(MissionOffer& offer, const GPoint& sitePoint, uint16 siteTypeID)
{
    if (offer.bookmarks != nullptr) {
        PySafeDecRef(offer.bookmarks);
        offer.bookmarks = nullptr;
    }
    offer.bookmarks = new PyList();

    // --- combat site (pickup) -----------------------------------------
    PyDict* site = new PyDict();
    site->SetItemString("itemID", new PyInt(offer.dungeonLocationID ? offer.dungeonLocationID : 0));
    site->SetItemString("typeID", new PyInt(siteTypeID)); // the transport holding the goods
    site->SetItemString("agentID", new PyInt(offer.agentID));
    {
        std::string hint = offer.name + " - Combat Site";
        site->SetItemString("hint", new PyString(hint.c_str()));
    }
    site->SetItemString("locationType", new PyString("objective.source"));
    site->SetItemString("memo", new PyString(""));
    site->SetItemString("created", new PyLong((int64)GetFileTimeNow()));
    site->SetItemString("locationNumber", new PyInt(0));
    site->SetItemString("flag", PyStatic.NewNone());
    site->SetItemString("locationID", new PyInt(offer.dungeonSolarSystemID));
    site->SetItemString("ownerID", new PyInt(offer.characterID));
    site->SetItemString("x", new PyFloat(sitePoint.x));
    site->SetItemString("y", new PyFloat(sitePoint.y));
    site->SetItemString("z", new PyFloat(sitePoint.z));
    site->SetItemString("solarsystemID", new PyInt(offer.dungeonSolarSystemID));
    offer.bookmarks->AddItem(new PyObject("util.KeyVal", site));

    // --- agent station (return / drop-off) ----------------------------
    PyDict* agentBm = new PyDict();
    agentBm->SetItemString("itemID", new PyInt(offer.destinationID));
    agentBm->SetItemString("typeID", new PyInt(offer.destinationTypeID));
    agentBm->SetItemString("agentID", new PyInt(offer.agentID));
    {
        std::string hint = offer.name + " - Agent Base";
        agentBm->SetItemString("hint", new PyString(hint.c_str()));
    }
    agentBm->SetItemString("locationType", new PyString("objective.destination"));
    agentBm->SetItemString("memo", new PyString(""));
    agentBm->SetItemString("created", new PyLong((int64)GetFileTimeNow()));
    agentBm->SetItemString("locationNumber", new PyInt(0));
    agentBm->SetItemString("flag", PyStatic.NewNone());
    agentBm->SetItemString("locationID", new PyInt(offer.destinationSystemID));
    agentBm->SetItemString("ownerID", new PyInt(offer.characterID));
    // NOTE: float, not int -- the site bookmark above sends PyFloat for x/y/z
    // and the client unpacks both bookmarks through the same path.  Mixing
    // PyInt and PyFloat here is exactly the kind of thing that makes the
    // journal silently drop a bookmark.
    agentBm->SetItemString("x", new PyFloat(0.0));
    agentBm->SetItemString("y", new PyFloat(0.0));
    agentBm->SetItemString("z", new PyFloat(0.0));
    agentBm->SetItemString("solarsystemID", new PyInt(offer.destinationSystemID));
    offer.bookmarks->AddItem(new PyObject("util.KeyVal", agentBm));
}

// SECMISSION-M2: custom mission prose (ids >= 56000).  Same mechanism as string
// titles -- the client accepts a string where a messageID would go.
//
// Backed by qstKill.briefing rather than a hardcoded switch: mission text is
// content, not code, and rewriting a briefing should not cost a server rebuild.
// Empty return = caller falls back to the numeric briefingID.
std::string MissionDataMgr::GetCustomBriefing(uint16 missionID)
{
    auto itr = m_killText.find(missionID);
    if (itr == m_killText.end())
        return std::string();
    return itr->second.briefing;
}

// SECMISSION-M3: the line the site's leader delivers when the pilot lands.
std::string MissionDataMgr::GetLeaderLine(uint16 missionID)
{
    auto itr = m_killText.find(missionID);
    if (itr == m_killText.end())
        return std::string();
    return itr->second.leaderLine;
}

// SECMISSION-M3: tag an NPC so that when it dies its wreck contains the mission
// goal item.  This is what makes "kill the transport, take the reports off the
// wreck" work instead of parking the objective in a free-floating can.
void MissionDataMgr::RegisterMissionDrop(uint32 npcItemID, uint16 goalTypeID, uint16 goalQty)
{
    if ((npcItemID == 0) or (goalTypeID == 0) or (goalQty == 0))
        return;
    MissionDrop drop;
    drop.typeID = goalTypeID;
    drop.qty    = goalQty;
    m_missionDrops[npcItemID] = drop;
    _log(AGENT__MESSAGE, "RegisterMissionDrop - npc %u will drop %u x%u", npcItemID, goalTypeID, goalQty);
}

// SECMISSION-M3: called from NPC::Killed once the wreck exists.  Spawns the
// goal item straight into the wreck container, then clears the tag so a
// respawned itemID can never inherit a stale drop.
bool MissionDataMgr::InjectMissionLoot(uint32 npcItemID, uint32 wreckItemID)
{
    auto itr = m_missionDrops.find(npcItemID);
    if (itr == m_missionDrops.end())
        return false;

    const MissionDrop drop = itr->second;
    m_missionDrops.erase(itr);      // one-shot: consume the tag

    if (wreckItemID == 0) {
        _log(AGENT__ERROR, "InjectMissionLoot - npc %u died with no wreck; goal item %u LOST.  Mission is now uncompletable.",
             npcItemID, drop.typeID);
        return false;
    }

    // the item must be ADDED to the wreck's live container, exactly like
    // SystemEntity::DropLoot does -- spawning it with the wreck as bare
    // locationID corrupts the container's inventory (live: segfault the
    // moment the mission transport died)
    WreckContainerRef wreckRef = sItemFactory.GetWreckContainer(wreckItemID);
    if (wreckRef.get() == nullptr) {
        _log(AGENT__ERROR, "InjectMissionLoot - wreck %u has no container ref; goal item %u LOST.",
             wreckItemID, drop.typeID);
        return false;
    }

    ItemData goalData(drop.typeID, ownerSystem, wreckItemID, flagNone, drop.qty);
    InventoryItemRef goalRef = sItemFactory.SpawnItem(goalData);
    if (goalRef.get() == nullptr) {
        _log(AGENT__ERROR, "InjectMissionLoot - failed to spawn goal item %u x%u into wreck %u.  Mission is now uncompletable.",
             drop.typeID, drop.qty, wreckItemID);
        return false;
    }
    wreckRef->AddItem(goalRef);

    _log(AGENT__MESSAGE, "InjectMissionLoot - dropped %u x%u into wreck %u (from npc %u)",
         drop.typeID, drop.qty, wreckItemID, npcItemID);
    return true;
}

// SECMISSION-M3b: acceleration-gate -> pocket registry
void MissionDataMgr::RegisterMissionGate(uint32 gateItemID, uint16 missionID, const GPoint& pocket)
{
    if (gateItemID == 0)
        return;
    GatePocket gp;
    gp.point = pocket;
    gp.missionID = missionID;
    m_gatePockets[gateItemID] = gp;
    _log(AGENT__MESSAGE, "RegisterMissionGate - gate %u -> pocket (%.0f, %.0f, %.0f) for mission %u",
         gateItemID, pocket.x, pocket.y, pocket.z, missionID);
}

bool MissionDataMgr::GetMissionGatePocket(uint32 gateItemID, GPoint& pocket, uint16& missionID)
{
    auto itr = m_gatePockets.find(gateItemID);
    if (itr == m_gatePockets.end())
        return false;
    pocket = itr->second.point;
    missionID = itr->second.missionID;
    return true;
}
