import { useEffect, useCallback, useRef } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { useParams } from 'react-router-dom';
import {
  fetchContacts,
  fetchContactDetail,
  toggleFavorite,
  createContact,
  updateContact,
  deleteContact,
  setSearch,
  selectContact,
  clearContactSelection,
  setEditing,
  selectContacts,
  selectContactsTotal,
  selectContactsListStatus,
  selectContactsSearch,
  selectSelectedContactId,
  selectContactDetail,
  selectContactDetailStatus,
  selectIsEditing,
} from '../store/contactsSlice';
import ContactList from '../components/contacts/ContactList';
import ContactDetail from '../components/contacts/ContactDetail';
import ContactEditor from '../components/contacts/ContactEditor';
import styles from './Contacts.module.css';

export default function Contacts() {
  const dispatch = useDispatch();
  const { contactId: urlContactId } = useParams();

  const contacts = useSelector(selectContacts);
  const total = useSelector(selectContactsTotal);
  const listStatus = useSelector(selectContactsListStatus);
  const search = useSelector(selectContactsSearch);
  const selectedId = useSelector(selectSelectedContactId);
  const contactDetail = useSelector(selectContactDetail);
  const detailStatus = useSelector(selectContactDetailStatus);
  const isEditing = useSelector(selectIsEditing);

  const debounceRef = useRef(null);
  const pageRef = useRef(1);

  /* Initial fetch */
  useEffect(() => {
    dispatch(fetchContacts({}));
  }, [dispatch]);

  /* Deep-link: auto-select contact from URL param */
  useEffect(() => {
    if (urlContactId && urlContactId !== selectedId) {
      dispatch(selectContact(urlContactId));
      dispatch(fetchContactDetail(urlContactId));
    }
  }, [urlContactId, selectedId, dispatch]);

  /* Debounced search */
  const handleSearchChange = useCallback(
    (value) => {
      dispatch(setSearch(value));
      clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => {
        pageRef.current = 1;
        dispatch(fetchContacts({ search: value }));
      }, 300);
    },
    [dispatch]
  );

  /* Select a contact */
  const handleSelect = useCallback(
    (contactId) => {
      dispatch(selectContact(contactId));
      dispatch(fetchContactDetail(contactId));
    },
    [dispatch]
  );

  /* Toggle favorite */
  const handleToggleFavorite = useCallback(
    (contactId) => {
      dispatch(toggleFavorite(contactId));
    },
    [dispatch]
  );

  /* Load more */
  const handleLoadMore = useCallback(() => {
    pageRef.current += 1;
    dispatch(fetchContacts({ search, page: pageRef.current }));
  }, [dispatch, search]);

  /* Add new contact */
  const handleAddNew = useCallback(() => {
    dispatch(clearContactSelection());
    dispatch(setEditing(true));
  }, [dispatch]);

  /* Edit existing */
  const handleEdit = useCallback(() => {
    dispatch(setEditing(true));
  }, [dispatch]);

  /* Save (create or update) */
  const handleSave = useCallback(
    (formData) => {
      if (selectedId) {
        dispatch(updateContact({ contactId: selectedId, data: formData }));
      } else {
        dispatch(createContact(formData));
      }
    },
    [dispatch, selectedId]
  );

  /* Cancel edit */
  const handleCancelEdit = useCallback(() => {
    dispatch(setEditing(false));
    if (!selectedId) dispatch(clearContactSelection());
  }, [dispatch, selectedId]);

  /* Delete */
  const handleDelete = useCallback(
    (contactId) => {
      if (window.confirm('Delete this contact?')) {
        dispatch(deleteContact(contactId));
      }
    },
    [dispatch]
  );

  /* Compose email to contact */
  const handleComposeEmail = useCallback((address, name) => {
    window.dispatchEvent(
      new CustomEvent('devemail:compose', {
        detail: { to: [{ address, name }] },
      })
    );
  }, []);

  const hasMore = contacts.length < total;

  return (
    <div className={styles.contacts}>
      {/* Left panel — contact list */}
      <div className={styles.listPanel}>
        <ContactList
          contacts={contacts}
          total={total}
          status={listStatus}
          search={search}
          selectedId={selectedId}
          onSearchChange={handleSearchChange}
          onSelect={handleSelect}
          onToggleFavorite={handleToggleFavorite}
          onAddNew={handleAddNew}
          onLoadMore={handleLoadMore}
          hasMore={hasMore}
        />
      </div>

      {/* Right panel — detail or editor */}
      <div className={styles.detailPanel}>
        {isEditing ? (
          <ContactEditor
            contact={selectedId ? contactDetail : null}
            onSave={handleSave}
            onCancel={handleCancelEdit}
          />
        ) : (
          <ContactDetail
            contact={contactDetail}
            status={detailStatus}
            onEdit={handleEdit}
            onDelete={handleDelete}
            onToggleFavorite={handleToggleFavorite}
            onComposeEmail={handleComposeEmail}
          />
        )}
      </div>
    </div>
  );
}
