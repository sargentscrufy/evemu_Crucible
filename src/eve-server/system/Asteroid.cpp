/*
 * Asteroid.cpp
 *
 * asteroid item and entity classes for EVEmu
 *
 * Original file/code by Zhur
 * Rewrite:     Allan
 */


#include "eve-server.h"

#include "EVEServerConfig.h"
#include "system/DestinyManager.h"
#include "system/Asteroid.h"
#include "system/SystemManager.h"
#include "system/cosmicMgrs/BeltMgr.h"
#include "system/SystemBubble.h"


AsteroidItem::AsteroidItem(const ItemType& type, const ItemData& idata, const AsteroidData& adata)
: InventoryItem(adata.itemID, type, idata),
m_data(adata)
{
    _log(ITEM__TRACE, "Created AsteroidItem for %s(%u).", adata.itemName.c_str(), adata.itemID);
}

AsteroidItemRef AsteroidItem::Load( uint32 asteroidID)
{
    return InventoryItem::Load<AsteroidItem>(asteroidID );
}

AsteroidItemRef AsteroidItem::Spawn(ItemData& idata, AsteroidData& adata) {
    const ItemType *type = sItemFactory.GetType(adata.typeID);
    if (type == nullptr)
        return AsteroidItemRef(nullptr);

    idata.name = type->name();
    adata.itemName = type->name();

    ManagerDB::CreateRoidItemID(idata, adata);
    if (adata.itemID == 0)
        return AsteroidItemRef(nullptr);

    AsteroidItemRef roidRef = AsteroidItemRef(new AsteroidItem(*type, idata, adata));
    roidRef->SetAttribute(AttrRadius,    adata.radius);
    roidRef->SetAttribute(AttrQuantity,  adata.quantity);
    roidRef->SetAttribute(AttrVolume,    type->volume());
    roidRef->SetAttribute(AttrMass,      type->mass() * adata.quantity);

    return roidRef;
}

AsteroidItemRef AsteroidItem::SpawnTemp(ItemData& idata, AsteroidData& adata) {
    const ItemType *type = sItemFactory.GetType(adata.typeID);
    if (type == nullptr)
        return AsteroidItemRef(nullptr);

    idata.name = type->name();
    adata.itemName = type->name();
    adata.itemID = sItemFactory.GetNextTempID();

    AsteroidItemRef roidRef = AsteroidItemRef(new AsteroidItem(*type, idata, adata));
    roidRef->SetAttribute(AttrRadius,    adata.radius);
    roidRef->SetAttribute(AttrQuantity,  adata.quantity);
    roidRef->SetAttribute(AttrVolume,    type->volume());
    roidRef->SetAttribute(AttrMass,      type->mass() * adata.quantity);

    return roidRef;
}

//iRef = InventoryItem::SpawnItem(sItemFactory.GetNextTempID(), iData);

AsteroidSE::AsteroidSE(InventoryItemRef self, EVEServiceManager& services, SystemManager* system)
: ObjectSystemEntity(self, services, system),
m_growTimer(sConfig.cosmic.BeltGrowth *60 *60 *1000)  // hours->ms
{
    m_growTimer.Disable();

    // ROID-1: asteroids spawn with no HP or damage resonances, so weapon
    // damage either zeroed out or one-shot them.  Give them real structure
    // scaled by ore content (destroyable by design on this server, but not
    // in one volley) and unity resonances so the shield->armor->hull damage
    // math passes through cleanly (shield/armor stay at zero capacity).
    if (m_self->GetAttribute(AttrHP).get_float() < 1.0f) {
        float qty = m_self->GetAttribute(AttrQuantity).get_float();
        float hp = 500.0f + (qty * 0.15f);
        m_self->SetAttribute(AttrHP, hp);
        m_self->SetAttribute(AttrDamage, EvilZero);
        m_self->SetAttribute(AttrShieldKineticDamageResonance, 1.0f);
        m_self->SetAttribute(AttrShieldThermalDamageResonance, 1.0f);
        m_self->SetAttribute(AttrShieldEmDamageResonance, 1.0f);
        m_self->SetAttribute(AttrShieldExplosiveDamageResonance, 1.0f);
        m_self->SetAttribute(AttrArmorKineticDamageResonance, 1.0f);
        m_self->SetAttribute(AttrArmorThermalDamageResonance, 1.0f);
        m_self->SetAttribute(AttrArmorEmDamageResonance, 1.0f);
        m_self->SetAttribute(AttrArmorExplosiveDamageResonance, 1.0f);
        m_self->SetAttribute(AttrKineticDamageResonance, 1.0f);
        m_self->SetAttribute(AttrThermalDamageResonance, 1.0f);
        m_self->SetAttribute(AttrEmDamageResonance, 1.0f);
        m_self->SetAttribute(AttrExplosiveDamageResonance, 1.0f);
    }
}

void AsteroidSE::Process() {
    /* called by EntityList::Process on every loop */
    /*  Enable base call to Process Targeting and Movement  */
    SystemEntity::Process();

    if (m_growTimer.Check())
        if (!m_system->GetBeltMgr()->IsActive(m_bubble->GetID()))
            Grow();
}

void AsteroidSE::EncodeDestiny( Buffer& into )
{
    using namespace Destiny;

    BallHeader head = BallHeader();
        head.entityID = GetID();
        head.mode = Ball::Mode::RIGID;
        head.radius = GetRadius();
        head.posX = x();
        head.posY = y();
        head.posZ = z();
        head.flags = 0;
    into.Append( head );
    RIGID_Struct main;
        main.formationID = 0xFF;
    into.Append( main );

    _log(SE__DESTINY, "AsteroidSE::EncodeDestiny(): %s - id:%lli, mode:%u, flags:0x%X", GetName(), head.entityID, head.mode, head.flags);
}

void AsteroidSE::MakeDamageState(DoDestinyDamageState &into) {
    // ROID-1: report the real structure fraction so weapon damage is
    // visible on a targeted asteroid (shield/armor have no capacity).
    float hp = m_self->GetAttribute(AttrHP).get_float();
    float dmg = m_self->GetAttribute(AttrDamage).get_float();
    into.shield = 0.0;
    into.recharge = 30000;
    into.timestamp = GetFileTimeNow();
    into.armor = 0.0;
    into.structure = (hp > 0.0f) ? EvE::max(0.0f, 1.0f - (dmg / hp)) : 1.0;
}

void AsteroidSE::SendDamageStateChanged() {  //working 24Apr15
    DoDestinyDamageState dmgState;
    MakeDamageState(dmgState);
    OnDamageStateChange dmgChange;
    dmgChange.entityID = m_self->itemID();
    dmgChange.state = dmgState.Encode();
    PyTuple *up = dmgChange.Encode();
    if (m_targMgr != nullptr)
        m_targMgr->QueueUpdate(&up);
    PySafeDecRef(up);
}

void AsteroidSE::Grow() {
    /*  not real sure how to implement this
     * maybe use internal data structure to hold sizes (current, possible) and time interval
     * use this to check/update current sizes (radius and mass)
     *
     * currently sets quantity back to full and disables m_growTimer
     *   - not gonna work...radius is set to quantity AFTER being mined...
     */

    //double quantity = ((25000 * log(GetRadius())) - 112404.8);
    //m_self->SetAttribute(AttrQuantity,  quantity);   // quantity in m^3

    m_growTimer.Disable();
}

void AsteroidSE::Delete()
{
    _log(SPAWN__DEPOP, "AsteroidSE::Delete() - Removing asteroid %s(%u) from beltID %u", \
            m_self->name(), m_self->itemID(), m_beltID);
    m_beltMgr->RemoveAsteroid(m_beltID, this);
    SystemEntity::Delete();
}

/*
 * def ComputeRadiusFromQuantity(categoryID, groupID, typeID, quantity):
 *    if quantity < 0:
 *        quantity = 1
 *    if categoryID == const.categoryAsteroid:
 *        qty = quantity
 *        if qty > 130000:
 *            qty = 130000
 *        return 89.675 * math.exp(4e-05 * qty)
 *    if groupID == const.groupHarvestableCloud:
 *        return quantity * cfg.invtypes.Get(typeID).radius / 10.0
 *    return quantity * cfg.invtypes.Get(typeID).radius
 *
 *
 * def ComputeQuantityFromRadius(categoryID, groupID, typeID, radius):
 *    if categoryID == const.categoryAsteroid:
 *        quantity = math.log(radius / 89.675) * (1.0 / 4e-05)
 *        return quantity
 *    if groupID == const.groupHarvestableCloud:
 *        quantity = radius * 10.0 / cfg.invtypes.Get(typeID).radius
 *        return quantity
 *    return radius / cfg.invtypes.Get(typeID).radius
 */