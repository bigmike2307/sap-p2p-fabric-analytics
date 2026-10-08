@AbapCatalog.viewEnhancementCategory: [#NONE]
@AccessControl.authorizationCheck: #NOT_REQUIRED
@EndUserText.label: 'P2P extraction: purchase order header'
@Metadata.ignorePropagatedAnnotations: true
@ObjectModel.usageType: { serviceQuality: #D, sizeCategory: #L, dataClass: #TRANSACTIONAL }
@Analytics.dataCategory: #FACT
@Analytics.dataExtraction.enabled: true
@Analytics.dataExtraction.delta.changeDataCapture.automatic: true
define view entity ZX_P2P_EKKO
  as select from ekko
{
  key ebeln,
      bukrs,
      bstyp,
      bsart,
      lifnr,
      ekorg,
      ekgrp,
      waers,
      bedat,
      aedat,
      ernam,
      zterm,
      frgke
}
where
  bstyp = 'F' // purchase orders only: no contracts, scheduling agreements or RFQs
